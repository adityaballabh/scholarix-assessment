from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import get_args
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from merge_review.config import get_settings
from merge_review.database import get_session
from merge_review.generate_cases import normalized_words
from merge_review.models import (
    ActivityEvent,
    Author,
    CaseEvidence,
    DatasetSnapshot,
    IdentityCandidate,
    IdentityCandidatePublication,
    PublicationRecord,
    ReviewDecision,
    SourceRecord,
    ValidationCase,
)
from merge_review.schemas import (
    ActivityEventResponse,
    AuthorIdentityDetail,
    CasePriority,
    ClusterPublication,
    DecisionRequest,
    EvidenceRecord,
    ReviewOverview,
    ReviewStatus,
    ReviewTarget,
    SemanticScholarCandidate,
    SourceRecordReference,
    SourceStatus,
    ValidationCaseResponse,
)

router = APIRouter(prefix="/api")
VALID_STATUSES = set(get_args(ReviewStatus))
SOURCE_ORDER = {
    "openalex": 0,
    "orcid": 1,
    "crossref": 2,
    "datacite": 3,
    "doi": 4,
    "semantic_scholar": 5,
}
SOURCE_FAILURE_ORDER = ["rate_limited", "timeout", "error", "pending"]
ACTION_STATUS = {
    "reopen": "pending",
    "confirm_one_author": "one_author",
    "flag_for_split": "needs_split",
    "mark_uncertain": "uncertain",
    "defer": "deferred",
}


def latest_snapshot(session: Session) -> DatasetSnapshot | None:
    return session.scalar(
        select(DatasetSnapshot).order_by(DatasetSnapshot.imported_at.desc()).limit(1)
    )


def utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def matches_author_name(author_name: str, query: str) -> bool:
    name_tokens = normalized_words(author_name)
    return all(
        any(name_token.startswith(query_token) for name_token in name_tokens)
        for query_token in normalized_words(query)
    )


def case_response(session: Session, review_case: ValidationCase) -> ValidationCaseResponse:
    author = session.get(Author, review_case.author_id)
    if author is None:
        raise RuntimeError(f"Case {review_case.id} has no author")

    evidence = session.scalars(
        select(CaseEvidence)
        .where(CaseEvidence.case_id == review_case.id)
        .order_by(CaseEvidence.position)
    ).all()
    candidates = session.scalars(
        select(IdentityCandidate)
        .where(IdentityCandidate.case_id == review_case.id)
        .order_by(IdentityCandidate.position)
    ).all()
    candidate_ids = [candidate.id for candidate in candidates]
    publications_by_candidate: dict[UUID, list[IdentityCandidatePublication]] = defaultdict(list)
    if candidate_ids:
        publications = session.scalars(
            select(IdentityCandidatePublication)
            .where(IdentityCandidatePublication.identity_candidate_id.in_(candidate_ids))
            .order_by(
                IdentityCandidatePublication.identity_candidate_id,
                IdentityCandidatePublication.position,
            )
        )
        for publication in publications:
            publications_by_candidate[publication.identity_candidate_id].append(publication)

    candidate_responses = [
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
        for candidate in candidates
    ]
    topics = author.profile.get("topics") if isinstance(author.profile, dict) else []

    return ValidationCaseResponse(
        id=review_case.id,
        status=review_case.status,
        priority=review_case.priority,
        target=ReviewTarget(
            author_slug=author.slug,
            author_name=author.name,
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
            candidate_ids=candidate_responses,
            top_share=candidate_responses[0].share if candidate_responses else None,
            profile_topics=[topic for topic in topics or [] if isinstance(topic, str)],
        ),
    )


def parse_statuses(value: str | None) -> set[str] | None:
    if value is None:
        return None
    statuses = {status for status in value.split(",") if status}
    invalid = statuses - VALID_STATUSES
    if invalid:
        raise HTTPException(422, detail=f"Unknown review status: {', '.join(sorted(invalid))}")
    return statuses


@router.get("/cases", response_model=list[ValidationCaseResponse])
def list_cases(
    status: str | None = None,
    priority: CasePriority | None = None,
    query: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> list[ValidationCaseResponse]:
    snapshot = latest_snapshot(session)
    if snapshot is None:
        return []

    statuses = parse_statuses(status)
    statement = (
        select(ValidationCase)
        .join(Author)
        .where(ValidationCase.dataset_snapshot_id == snapshot.id)
        .order_by(
            case((ValidationCase.status == "deferred", 1), else_=0),
            case(
                (ValidationCase.priority == "high", 0),
                (ValidationCase.priority == "medium", 1),
                else_=2,
            ),
            desc(ValidationCase.affected_count),
            ValidationCase.id,
        )
    )
    if statuses:
        statement = statement.where(ValidationCase.status.in_(statuses))
    if priority:
        statement = statement.where(ValidationCase.priority == priority)

    rows = list(session.scalars(statement))
    if query:
        rows = [
            row
            for row in rows
            if matches_author_name(session.get(Author, row.author_id).name, query)
        ]
    rows = rows[offset : offset + limit]
    return [case_response(session, row) for row in rows]


@router.get("/cases/{case_id}", response_model=ValidationCaseResponse)
def get_case(case_id: str, session: Session = Depends(get_session)) -> ValidationCaseResponse:
    review_case = session.get(ValidationCase, case_id)
    if review_case is None:
        raise HTTPException(404, detail="Case not found")
    return case_response(session, review_case)


def activity_response(event: ActivityEvent) -> ActivityEventResponse:
    return ActivityEventResponse(
        id=str(event.id),
        case_id=event.case_id,
        action_type=event.action_type,
        actor=event.actor,
        created_at=utc_datetime(event.created_at),
        target_name=event.target_name,
        note=event.note,
        before=event.before_status,
        after=event.after_status,
    )


@router.post("/cases/{case_id}/decisions", response_model=ActivityEventResponse)
def post_decision(
    case_id: str,
    request: DecisionRequest,
    session: Session = Depends(get_session),
) -> ActivityEventResponse:
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
    reviewer_id = get_settings().reviewer_id
    event = ActivityEvent(
        id=uuid4(),
        decision_id=decision_id,
        case_id=review_case.id,
        action_type=request.action,
        actor=reviewer_id,
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
        reviewer_id=reviewer_id,
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


@router.get("/activity", response_model=list[ActivityEventResponse])
def list_activity(session: Session = Depends(get_session)) -> list[ActivityEventResponse]:
    events = session.scalars(
        select(ActivityEvent).order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc())
    )
    return [activity_response(event) for event in events]


def source_state(counts: Counter[str]) -> str:
    for status in SOURCE_FAILURE_ORDER:
        if counts[status]:
            return status
    if counts["success"]:
        return "success"
    if counts["not_found"]:
        return "not_found"
    if counts["empty"]:
        return "empty"
    return "never_attempted"


def source_note(counts: Counter[str]) -> str:
    labels = {
        "success": "success",
        "not_found": "not found",
        "empty": "empty",
        "rate_limited": "rate limited",
        "timeout": "timed out",
        "error": "failed",
        "pending": "pending",
    }
    return "; ".join(
        f"{counts[status]} {label}" for status, label in labels.items() if counts[status]
    )


@router.get("/overview", response_model=ReviewOverview)
def get_overview(session: Session = Depends(get_session)) -> ReviewOverview:
    snapshot = latest_snapshot(session)
    if snapshot is None:
        return ReviewOverview(
            authors=0,
            publications=0,
            authors_audited=0,
            publications_audited=0,
            audited_at=None,
            by_priority={},
            sources=[],
        )

    review_cases = list(
        session.scalars(
            select(ValidationCase).where(ValidationCase.dataset_snapshot_id == snapshot.id)
        )
    )
    authors_audited = session.scalar(
        select(func.count(Author.id)).where(Author.dataset_snapshot_id == snapshot.id)
    )
    publications_audited = session.scalar(
        select(func.count(PublicationRecord.id))
        .join(Author)
        .where(Author.dataset_snapshot_id == snapshot.id)
    )
    source_rows = session.execute(
        select(
            SourceRecord.source,
            SourceRecord.fetch_status,
            func.count(),
            func.max(SourceRecord.fetched_at),
        )
        .where(SourceRecord.dataset_snapshot_id == snapshot.id)
        .group_by(SourceRecord.source, SourceRecord.fetch_status)
    ).all()
    counts_by_source: dict[str, Counter[str]] = defaultdict(Counter)
    fetched_by_source: dict[str, datetime | None] = {}
    for source, status, count, fetched_at in source_rows:
        counts_by_source[source][status] = count
        previous = fetched_by_source.get(source)
        if previous is None or fetched_at > previous:
            fetched_by_source[source] = fetched_at

    sources = [
        SourceStatus(
            source=source,
            fetched_at=utc_datetime(fetched_by_source.get(source)),
            state=source_state(counts),
            note=source_note(counts),
        )
        for source, counts in sorted(
            counts_by_source.items(),
            key=lambda item: (SOURCE_ORDER.get(item[0], len(SOURCE_ORDER)), item[0]),
        )
    ]
    audited_at = max(
        (fetched_at for fetched_at in fetched_by_source.values() if fetched_at is not None),
        default=None,
    )

    return ReviewOverview(
        authors=len(review_cases),
        publications=sum(review_case.affected_count for review_case in review_cases),
        authors_audited=authors_audited or 0,
        publications_audited=publications_audited or 0,
        audited_at=utc_datetime(audited_at),
        by_priority=dict(Counter(review_case.priority for review_case in review_cases)),
        sources=sources,
    )
