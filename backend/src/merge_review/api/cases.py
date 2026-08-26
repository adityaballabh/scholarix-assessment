from collections import defaultdict
from datetime import UTC, datetime
from typing import get_args
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case as sql_case
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from merge_review.api.activity import activity_response
from merge_review.api.common import ensure_fetch_idle, latest_snapshot, utc_datetime
from merge_review.cases.naming import normalized_words
from merge_review.database import get_session
from merge_review.models import (
    ActivityEvent,
    Author,
    CaseEvidence,
    DatasetSnapshot,
    IdentityCandidate,
    IdentityCandidatePublication,
    ReviewDecision,
    SourceRecord,
    User,
    ValidationCase,
)
from merge_review.schemas import (
    ActivityEventResponse,
    AuthorIdentityDetail,
    ClusterPublication,
    DecisionRequest,
    EvidenceRecord,
    PriorityComponents,
    PriorityConfig,
    QueueScope,
    ReviewStatus,
    ReviewTarget,
    SemanticScholarCandidate,
    SourceRecordReference,
    ValidationCaseResponse,
)
from merge_review.security import get_current_user

router = APIRouter()
VALID_STATUSES = set(get_args(ReviewStatus))
ACTION_STATUS = {
    "reopen": "pending",
    "confirm_one_author": "one_author",
    "flag_for_split": "needs_split",
    "mark_uncertain": "uncertain",
    "defer": "deferred",
}


def matches_author_name(author_name: str, query: str) -> bool:
    name_tokens = normalized_words(author_name)
    return all(
        any(name_token.startswith(query_token) for name_token in name_tokens)
        for query_token in normalized_words(query)
    )


def case_response(
    *,
    review_case: ValidationCase,
    author: Author,
    evidence: list[CaseEvidence],
    candidates: list[SemanticScholarCandidate],
    openalex_topics: list[str],
    dataset_imported_at: datetime,
) -> ValidationCaseResponse:
    return ValidationCaseResponse(
        id=review_case.id,
        dataset_imported_at=dataset_imported_at,
        status=review_case.status,
        queue_eligible=review_case.queue_eligible,
        priority_score=review_case.priority_score,
        priority_components=PriorityComponents.model_validate(review_case.priority_components),
        priority_config=PriorityConfig.model_validate(review_case.priority_config),
        target=ReviewTarget(
            author_slug=author.slug,
            author_name=author.name,
            author_affiliation=author.affiliation,
            openalex_id=author.source_id,
        ),
        affected_count=review_case.affected_count,
        version=review_case.version,
        evidence=[
            EvidenceRecord(
                source=row.source,
                source_refs=[SourceRecordReference.model_validate(ref) for ref in row.source_refs],
                fetched_at=utc_datetime(row.fetched_at),
                fetch_status=row.fetch_status,
                field=row.field,
                value=row.value,
                value_state=row.value_state,
                interpretation=row.interpretation,
            )
            for row in evidence
        ],
        detail=AuthorIdentityDetail(
            candidate_ids=candidates,
            top_share=candidates[0].share if candidates else None,
            openalex_topics=openalex_topics,
        ),
    )


def case_responses(
    session: Session,
    case_rows: list[tuple[ValidationCase, Author]],
) -> list[ValidationCaseResponse]:
    if not case_rows:
        return []

    case_ids = [review_case.id for review_case, _ in case_rows]
    evidence_by_case: dict[str, list[CaseEvidence]] = defaultdict(list)
    for row in session.scalars(
        select(CaseEvidence)
        .where(CaseEvidence.case_id.in_(case_ids))
        .order_by(CaseEvidence.case_id, CaseEvidence.position)
    ):
        evidence_by_case[row.case_id].append(row)

    candidates_by_case: dict[str, list[IdentityCandidate]] = defaultdict(list)
    candidate_rows = list(
        session.scalars(
            select(IdentityCandidate)
            .where(IdentityCandidate.case_id.in_(case_ids))
            .order_by(IdentityCandidate.case_id, IdentityCandidate.position)
        )
    )
    for candidate in candidate_rows:
        candidates_by_case[candidate.case_id].append(candidate)

    publications_by_candidate: dict[UUID, list[IdentityCandidatePublication]] = defaultdict(list)
    candidate_ids = [candidate.id for candidate in candidate_rows]
    if candidate_ids:
        for publication in session.scalars(
            select(IdentityCandidatePublication)
            .where(IdentityCandidatePublication.identity_candidate_id.in_(candidate_ids))
            .order_by(
                IdentityCandidatePublication.identity_candidate_id,
                IdentityCandidatePublication.position,
            )
        ):
            publications_by_candidate[publication.identity_candidate_id].append(publication)

    snapshot_ids = {author.dataset_snapshot_id for _, author in case_rows}
    source_ids = {author.source_id for _, author in case_rows}
    imported_at_by_snapshot = {
        snapshot.id: utc_datetime(snapshot.imported_at)
        for snapshot in session.scalars(
            select(DatasetSnapshot).where(DatasetSnapshot.id.in_(snapshot_ids))
        )
    }
    openalex_by_author = {
        (record.dataset_snapshot_id, record.entity_key): record.payload
        for record in session.scalars(
            select(SourceRecord).where(
                SourceRecord.dataset_snapshot_id.in_(snapshot_ids),
                SourceRecord.source == "openalex",
                SourceRecord.entity_type == "author",
                SourceRecord.entity_key.in_(source_ids),
            )
        )
    }

    responses = []
    for review_case, author in case_rows:
        candidates = [
            SemanticScholarCandidate(
                id=candidate.semantic_scholar_author_id,
                share=candidate.share,
                first_year=candidate.first_year,
                last_year=candidate.last_year,
                publications=[
                    ClusterPublication(year=publication.year, title=publication.title)
                    for publication in publications_by_candidate[candidate.id]
                ],
            )
            for candidate in candidates_by_case[review_case.id]
        ]
        openalex_payload = openalex_by_author.get((author.dataset_snapshot_id, author.source_id))
        topics = openalex_payload.get("topics") if isinstance(openalex_payload, dict) else []
        responses.append(
            case_response(
                review_case=review_case,
                author=author,
                evidence=evidence_by_case[review_case.id],
                candidates=candidates,
                openalex_topics=[
                    topic["display_name"]
                    for topic in topics or []
                    if isinstance(topic, dict) and isinstance(topic.get("display_name"), str)
                ],
                dataset_imported_at=imported_at_by_snapshot[author.dataset_snapshot_id],
            )
        )
    return responses


def parse_statuses(value: str | None) -> set[str] | None:
    if value is None:
        return None
    statuses = {status for status in value.split(",") if status}
    invalid = statuses - VALID_STATUSES
    if invalid:
        raise HTTPException(422, detail=f"Unknown review status: {', '.join(sorted(invalid))}")
    return statuses


def filtered_case_rows(
    session: Session,
    status: str | None,
    scope: QueueScope,
    query: str | None,
    limit: int | None,
    offset: int,
) -> list[tuple[ValidationCase, Author]]:
    snapshot = latest_snapshot(session)
    if snapshot is None:
        return []

    statuses = parse_statuses(status)
    statement = (
        select(ValidationCase, Author)
        .join(Author)
        .where(
            ValidationCase.dataset_snapshot_id == snapshot.id,
            ValidationCase.queue_eligible == (scope == "active"),
        )
        .order_by(
            sql_case((ValidationCase.status == "deferred", 1), else_=0),
            desc(ValidationCase.priority_score),
            desc(ValidationCase.affected_count),
            ValidationCase.id,
        )
    )
    if statuses:
        statement = statement.where(ValidationCase.status.in_(statuses))

    if query:
        matched = [
            (review_case, author)
            for review_case, author in session.execute(statement)
            if matches_author_name(author.name, query)
        ]
        return matched[offset:] if limit is None else matched[offset : offset + limit]
    if limit is not None:
        statement = statement.limit(limit)
    return [
        (review_case, author) for review_case, author in session.execute(statement.offset(offset))
    ]


@router.get("/cases", response_model=list[ValidationCaseResponse])
def list_cases(
    status: str | None = None,
    scope: QueueScope = "active",
    query: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> list[ValidationCaseResponse]:
    ensure_fetch_idle(session)
    rows = filtered_case_rows(session, status, scope, query, limit, offset)
    return case_responses(session, rows)


@router.get("/cases/{case_id}", response_model=ValidationCaseResponse)
def get_case(case_id: str, session: Session = Depends(get_session)) -> ValidationCaseResponse:
    ensure_fetch_idle(session)
    row = session.execute(
        select(ValidationCase, Author).join(Author).where(ValidationCase.id == case_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(404, detail="Case not found")
    return case_responses(session, [(row[0], row[1])])[0]


@router.post("/cases/{case_id}/decisions", response_model=ActivityEventResponse)
def post_decision(
    case_id: str,
    request: DecisionRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ActivityEventResponse:
    snapshot_id = session.scalar(
        select(ValidationCase.dataset_snapshot_id).where(ValidationCase.id == case_id)
    )
    if snapshot_id is None:
        raise HTTPException(404, detail="Case not found")
    session.scalar(
        select(DatasetSnapshot).where(DatasetSnapshot.id == snapshot_id).with_for_update(read=True)
    )
    ensure_fetch_idle(session)
    review_case = session.scalar(
        select(ValidationCase).where(ValidationCase.id == case_id).with_for_update()
    )
    if review_case is None:
        raise HTTPException(404, detail="Case not found")
    if review_case.version != request.expected_version:
        raise HTTPException(409, detail="Case changed after it was loaded")
    if request.action == "note" and request.note is None:
        raise HTTPException(422, detail="A note is required")

    before = review_case.status
    after = ACTION_STATUS.get(request.action, before)
    if request.action != "note" and after == before:
        raise HTTPException(409, detail="Case is already in that state")

    author = session.get(Author, review_case.author_id)
    if author is None:
        raise RuntimeError(f"Case {review_case.id} has no author")
    created_at = datetime.now(UTC)
    decision_id = uuid4()
    event = ActivityEvent(
        id=uuid4(),
        decision_id=decision_id,
        case_id=review_case.id,
        action_type=request.action,
        actor=current_user.display_name,
        target_name=author.name,
        note=request.note,
        before_status=before,
        after_status=after,
        created_at=created_at,
    )
    decision = ReviewDecision(
        id=decision_id,
        case_id=review_case.id,
        action=request.action,
        note=request.note,
        reviewer_id=current_user.id,
        expected_case_version=request.expected_version,
        created_at=created_at,
    )
    session.add(decision)
    session.flush()
    session.add(event)
    review_case.status = after
    review_case.version += 1
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
    return activity_response(event)
