from collections import defaultdict
from datetime import datetime
from typing import get_args
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case as sql_case
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from merge_review.api.common import utc_datetime
from merge_review.cases.naming import normalized_words
from merge_review.models import (
    Author,
    CaseEvidence,
    DatasetSnapshot,
    IdentityCandidate,
    IdentityCandidatePublication,
    SourceRecord,
    ValidationCase,
)
from merge_review.schemas import (
    AuthorIdentityDetail,
    ClusterPublication,
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

VALID_STATUSES = set(get_args(ReviewStatus))
STATUS_ORDER = ("pending", "one_author", "needs_split", "uncertain", "deferred")


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
    *,
    snapshot_id: UUID,
    status: str | None,
    scope: QueueScope,
    query: str | None,
    limit: int | None,
    offset: int,
) -> list[tuple[ValidationCase, Author]]:
    statuses = parse_statuses(status)
    top_share = (
        select(IdentityCandidate.share)
        .where(IdentityCandidate.case_id == ValidationCase.id, IdentityCandidate.position == 0)
        .scalar_subquery()
    )
    candidate_count = (
        select(func.count(IdentityCandidate.id))
        .where(IdentityCandidate.case_id == ValidationCase.id)
        .scalar_subquery()
    )
    statement = (
        select(ValidationCase, Author)
        .join(Author)
        .where(
            ValidationCase.dataset_snapshot_id == snapshot_id,
            ValidationCase.queue_eligible == (scope == "active"),
        )
        .order_by(
            desc(ValidationCase.priority_score),
            desc(func.coalesce(top_share, 0)),
            desc(candidate_count),
            desc(ValidationCase.affected_count),
            sql_case(
                {status: index for index, status in enumerate(STATUS_ORDER)},
                value=ValidationCase.status,
            ),
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
