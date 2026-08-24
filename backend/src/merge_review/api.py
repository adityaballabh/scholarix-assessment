from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import get_args
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from merge_review.audit import run_full_audit
from merge_review.audit_service import run_audit
from merge_review.config import get_settings
from merge_review.database import get_session
from merge_review.generate_cases import (
    default_review_settings,
    generate_identity_cases,
    normalized_words,
    review_settings,
)
from merge_review.import_dataset import normalize_doi
from merge_review.models import (
    ActivityEvent,
    AuditRun,
    Author,
    CaseEvidence,
    DatasetSnapshot,
    IdentityCandidate,
    IdentityCandidatePublication,
    PublicationRecord,
    ReviewDecision,
    ReviewSettings,
    ValidationCase,
)
from merge_review.refresh import (
    PUBLICATION_SOURCES,
    refresh_author_source,
    refresh_author_sources,
    refresh_publication_sources,
    refresh_source,
)
from merge_review.schemas import (
    ActivityEventResponse,
    AuditConfigResponse,
    AuditConfigUpdate,
    AuditResponse,
    AuditRunResponse,
    AuditSourceProgress,
    AuthorIdentityDetail,
    ClusterPublication,
    DecisionRequest,
    EvidenceRecord,
    PriorityComponents,
    PriorityConfig,
    QueueScope,
    RefreshResponse,
    RefreshSource,
    ReviewOverview,
    ReviewStatus,
    ReviewTarget,
    SemanticScholarCandidate,
    SourceRecordReference,
    SourceStatus,
    ValidationCaseResponse,
)
from merge_review.source_records import uncached_http_session

router = APIRouter(prefix="/api")
VALID_STATUSES = set(get_args(ReviewStatus))
OVERVIEW_SOURCE_STAGES = {
    "openalex": (
        "openalex_authors",
        "openalex_author_publications",
        "openalex_publications",
    ),
    "orcid": ("orcid",),
    "semantic_scholar": ("semantic_scholar",),
}
ACTION_STATUS = {
    "reopen": "pending",
    "confirm_one_author": "one_author",
    "flag_for_split": "needs_split",
    "mark_uncertain": "uncertain",
    "defer": "deferred",
}
ACTIVE_AUDIT_STATUSES = {"queued", "running"}


def latest_snapshot(session: Session) -> DatasetSnapshot | None:
    return session.scalar(
        select(DatasetSnapshot).order_by(DatasetSnapshot.imported_at.desc()).limit(1)
    )


def current_audit(session: Session) -> AuditRun | None:
    return session.scalar(
        select(AuditRun).order_by(AuditRun.created_at.desc(), AuditRun.id.desc()).limit(1)
    )


def last_completed_at(session: Session) -> datetime | None:
    return session.scalar(
        select(func.max(AuditRun.finished_at)).where(AuditRun.status == "complete")
    )


def latest_completed_fetch(session: Session, snapshot_id: UUID) -> AuditRun | None:
    return session.scalar(
        select(AuditRun)
        .where(
            AuditRun.dataset_snapshot_id == snapshot_id,
            AuditRun.status == "complete",
        )
        .order_by(AuditRun.finished_at.desc(), AuditRun.id.desc())
        .limit(1)
    )


def ensure_audit_idle(session: Session) -> None:
    audit = session.scalar(
        select(AuditRun)
        .where(AuditRun.status.in_(ACTIVE_AUDIT_STATUSES))
        .order_by(AuditRun.created_at.desc())
        .limit(1)
    )
    if audit is not None:
        raise HTTPException(423, detail="Audit in progress")


def audit_response(
    audit: AuditRun,
    completed_at: datetime | None,
) -> AuditRunResponse:
    return AuditRunResponse(
        id=str(audit.id),
        status=audit.status,
        current_source=audit.current_source,
        source_progress={
            source: AuditSourceProgress.model_validate(progress)
            for source, progress in (audit.source_progress or {}).items()
        },
        started_at=utc_datetime(audit.started_at),
        finished_at=utc_datetime(audit.finished_at),
        last_completed_at=utc_datetime(completed_at),
        error=audit.error,
    )


def lock_snapshot_cases(session: Session, snapshot_id: UUID) -> None:
    session.scalar(
        select(DatasetSnapshot).where(DatasetSnapshot.id == snapshot_id).with_for_update()
    )
    session.scalars(
        select(ValidationCase)
        .where(ValidationCase.dataset_snapshot_id == snapshot_id)
        .order_by(ValidationCase.id)
        .with_for_update()
    ).all()


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


def case_response(
    review_case: ValidationCase,
    author: Author,
    evidence: list[CaseEvidence],
    candidates: list[IdentityCandidate],
    publications_by_candidate: dict[UUID, list[IdentityCandidatePublication]],
) -> ValidationCaseResponse:
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
        queue_eligible=review_case.queue_eligible,
        priority_score=review_case.priority_score,
        priority_components=PriorityComponents.model_validate(review_case.priority_components),
        priority_config=PriorityConfig.model_validate(review_case.priority_config),
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
    candidates = list(
        session.scalars(
            select(IdentityCandidate)
            .where(IdentityCandidate.case_id.in_(case_ids))
            .order_by(IdentityCandidate.case_id, IdentityCandidate.position)
        )
    )
    for candidate in candidates:
        candidates_by_case[candidate.case_id].append(candidate)

    publications_by_candidate: dict[UUID, list[IdentityCandidatePublication]] = defaultdict(list)
    candidate_ids = [candidate.id for candidate in candidates]
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

    return [
        case_response(
            review_case,
            author,
            evidence_by_case[review_case.id],
            candidates_by_case[review_case.id],
            publications_by_candidate,
        )
        for review_case, author in case_rows
    ]


def audit_config_response(settings: ReviewSettings) -> AuditConfigResponse:
    return AuditConfigResponse(
        max_top_candidate_share=settings.max_top_candidate_share,
        weights=settings.priority_weights,
        version=settings.version,
        updated_at=utc_datetime(settings.updated_at),
    )


@router.get("/fetches/current", response_model=AuditRunResponse | None)
def get_audit(session: Session = Depends(get_session)) -> AuditRunResponse | None:
    audit = current_audit(session)
    return audit_response(audit, last_completed_at(session)) if audit else None


@router.post("/fetches", response_model=AuditRunResponse, status_code=202)
def start_audit(
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> AuditRunResponse:
    snapshot = session.scalar(
        select(DatasetSnapshot)
        .order_by(DatasetSnapshot.imported_at.desc())
        .limit(1)
        .with_for_update()
    )
    if snapshot is None:
        raise HTTPException(404, detail="No dataset imported")
    ensure_audit_idle(session)
    audit = AuditRun(
        dataset_snapshot_id=snapshot.id,
        status="queued",
        source_progress={},
    )
    session.add(audit)
    session.flush()
    session.refresh(audit)
    response = audit_response(audit, last_completed_at(session))
    session.commit()
    background_tasks.add_task(run_full_audit, audit.id, snapshot.id)
    return response


@router.post("/fetches/{fetch_id}/abandon", response_model=AuditRunResponse)
def abandon_audit(
    fetch_id: UUID,
    session: Session = Depends(get_session),
) -> AuditRunResponse:
    snapshot_id = session.scalar(
        select(AuditRun.dataset_snapshot_id).where(AuditRun.id == fetch_id)
    )
    if snapshot_id is None:
        raise HTTPException(404, detail="Audit not found")
    session.scalar(
        select(DatasetSnapshot).where(DatasetSnapshot.id == snapshot_id).with_for_update()
    )
    ensure_audit_idle(session)
    audit = session.scalar(select(AuditRun).where(AuditRun.id == fetch_id).with_for_update())
    if audit is None:
        raise HTTPException(404, detail="Audit not found")
    latest = current_audit(session)
    if latest is None or latest.id != audit.id:
        raise HTTPException(409, detail="Audit is no longer current")
    if audit.status != "failed":
        raise HTTPException(409, detail="Only a failed audit can be abandoned")
    audit.status = "abandoned"
    session.commit()
    session.refresh(audit)
    return audit_response(audit, last_completed_at(session))


@router.get("/audit-config", response_model=AuditConfigResponse)
def get_audit_config(session: Session = Depends(get_session)) -> AuditConfigResponse:
    snapshot = latest_snapshot(session)
    if snapshot is None:
        raise HTTPException(404, detail="No dataset imported")
    ensure_audit_idle(session)
    settings = session.get(ReviewSettings, snapshot.id) or default_review_settings(snapshot.id)
    return audit_config_response(settings)


@router.put("/audit-config", response_model=AuditConfigResponse)
def update_audit_config(
    request: AuditConfigUpdate,
    session: Session = Depends(get_session),
) -> AuditConfigResponse:
    snapshot = latest_snapshot(session)
    if snapshot is None:
        raise HTTPException(404, detail="No dataset imported")
    session.scalar(
        select(DatasetSnapshot).where(DatasetSnapshot.id == snapshot.id).with_for_update()
    )
    ensure_audit_idle(session)
    settings = session.scalar(
        select(ReviewSettings)
        .where(ReviewSettings.dataset_snapshot_id == snapshot.id)
        .with_for_update()
    )
    if settings is None:
        settings = review_settings(session, snapshot.id)
    if settings.version != request.expected_version:
        raise HTTPException(409, detail={"current_version": settings.version})

    settings.max_top_candidate_share = request.max_top_candidate_share
    settings.priority_weights = request.weights.model_dump()
    settings.version += 1
    session.commit()
    session.refresh(settings)
    return audit_config_response(settings)


@router.post("/audits", response_model=AuditResponse)
def create_audit(session: Session = Depends(get_session)) -> AuditResponse:
    snapshot = latest_snapshot(session)
    if snapshot is None:
        raise HTTPException(404, detail="No dataset imported")
    session.scalar(
        select(DatasetSnapshot).where(DatasetSnapshot.id == snapshot.id).with_for_update()
    )
    ensure_audit_idle(session)
    cases = run_audit(session, snapshot.id)
    settings = review_settings(session, snapshot.id)
    response = AuditResponse(config_version=settings.version, cases=cases)
    session.commit()
    return response


def refresh_response(
    scope: str,
    target: str,
    results: Counter[str],
    cases: int,
) -> RefreshResponse:
    return RefreshResponse(
        scope=scope,
        target=target,
        results=dict(sorted(results.items())),
        cases=cases,
    )


def author_for_slug(session: Session, snapshot_id: UUID, author_slug: str) -> Author:
    author = session.scalar(
        select(Author).where(
            Author.dataset_snapshot_id == snapshot_id,
            Author.slug == author_slug,
        )
    )
    if author is None:
        raise HTTPException(404, detail="Author not found")
    return author


@router.post("/refresh/authors/{author_slug}", response_model=RefreshResponse)
def refresh_author(
    author_slug: str,
    session: Session = Depends(get_session),
) -> RefreshResponse:
    snapshot = latest_snapshot(session)
    if snapshot is None:
        raise HTTPException(404, detail="No dataset imported")
    author = author_for_slug(session, snapshot.id, author_slug)

    lock_snapshot_cases(session, snapshot.id)
    ensure_audit_idle(session)
    with uncached_http_session() as http_session:
        results = refresh_author_sources(session, http_session, author)
    cases = generate_identity_cases(session, snapshot.id)
    session.commit()
    return refresh_response("author", author_slug, results, cases)


@router.post(
    "/refresh/authors/{author_slug}/sources/{source}",
    response_model=RefreshResponse,
)
def refresh_author_source_type(
    author_slug: str,
    source: RefreshSource,
    session: Session = Depends(get_session),
) -> RefreshResponse:
    snapshot = latest_snapshot(session)
    if snapshot is None:
        raise HTTPException(404, detail="No dataset imported")
    author = author_for_slug(session, snapshot.id, author_slug)
    if source == "orcid" and not author.orcid_id:
        raise HTTPException(409, detail="Author has no ORCID identifier")

    lock_snapshot_cases(session, snapshot.id)
    ensure_audit_idle(session)
    with uncached_http_session() as http_session:
        results = refresh_author_source(session, http_session, author, source)
    cases = generate_identity_cases(session, snapshot.id)
    session.commit()
    return refresh_response("author_source", author_slug, results, cases)


@router.post("/refresh/dois/{doi:path}", response_model=RefreshResponse)
def refresh_doi(doi: str, session: Session = Depends(get_session)) -> RefreshResponse:
    snapshot = latest_snapshot(session)
    if snapshot is None:
        raise HTTPException(404, detail="No dataset imported")
    normalized_doi = normalize_doi(doi)
    exists = session.scalar(
        select(PublicationRecord.id)
        .join(Author)
        .where(
            Author.dataset_snapshot_id == snapshot.id,
            PublicationRecord.normalized_doi == normalized_doi,
        )
        .limit(1)
    )
    if normalized_doi is None or exists is None:
        raise HTTPException(404, detail="DOI not found in the current dataset")

    lock_snapshot_cases(session, snapshot.id)
    ensure_audit_idle(session)
    with uncached_http_session() as http_session:
        results = refresh_publication_sources(
            session,
            http_session,
            snapshot.id,
            [normalized_doi],
            set(PUBLICATION_SOURCES),
        )
    cases = generate_identity_cases(session, snapshot.id)
    session.commit()
    return refresh_response("doi", normalized_doi, results, cases)


@router.post("/refresh/sources/{source}", response_model=RefreshResponse)
def refresh_source_type(
    source: RefreshSource,
    session: Session = Depends(get_session),
) -> RefreshResponse:
    snapshot = latest_snapshot(session)
    if snapshot is None:
        raise HTTPException(404, detail="No dataset imported")

    lock_snapshot_cases(session, snapshot.id)
    ensure_audit_idle(session)
    with uncached_http_session() as http_session:
        results = refresh_source(session, http_session, snapshot.id, source)
    cases = generate_identity_cases(session, snapshot.id)
    session.commit()
    return refresh_response("source", source, results, cases)


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
    scope: QueueScope = "active",
    query: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> list[ValidationCaseResponse]:
    snapshot = latest_snapshot(session)
    if snapshot is None:
        return []
    ensure_audit_idle(session)

    statuses = parse_statuses(status)
    statement = (
        select(ValidationCase, Author)
        .join(Author)
        .where(
            ValidationCase.dataset_snapshot_id == snapshot.id,
            ValidationCase.queue_eligible == (scope == "active"),
        )
        .order_by(
            case((ValidationCase.status == "deferred", 1), else_=0),
            desc(ValidationCase.priority_score),
            desc(ValidationCase.affected_count),
            ValidationCase.id,
        )
    )
    if statuses:
        statement = statement.where(ValidationCase.status.in_(statuses))

    if query:
        rows = [
            (review_case, author)
            for review_case, author in session.execute(statement)
            if matches_author_name(author.name, query)
        ][offset : offset + limit]
    else:
        rows = [
            (review_case, author)
            for review_case, author in session.execute(statement.limit(limit).offset(offset))
        ]
    return case_responses(session, rows)


@router.get("/cases/{case_id}", response_model=ValidationCaseResponse)
def get_case(case_id: str, session: Session = Depends(get_session)) -> ValidationCaseResponse:
    ensure_audit_idle(session)
    row = session.execute(
        select(ValidationCase, Author).join(Author).where(ValidationCase.id == case_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(404, detail="Case not found")
    return case_responses(session, [(row[0], row[1])])[0]


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
    snapshot_id = session.scalar(
        select(ValidationCase.dataset_snapshot_id).where(ValidationCase.id == case_id)
    )
    if snapshot_id is None:
        raise HTTPException(404, detail="Case not found")
    session.scalar(
        select(DatasetSnapshot).where(DatasetSnapshot.id == snapshot_id).with_for_update(read=True)
    )
    ensure_audit_idle(session)
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
    ensure_audit_idle(session)
    events = session.scalars(
        select(ActivityEvent).order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc())
    )
    return [activity_response(event) for event in events]


def source_state(counts: Counter[str]) -> str:
    successes = counts["success"]
    total = sum(counts.values())
    if not successes:
        return "unavailable"
    if successes == total:
        return "available"
    return "partially_available"


def source_note(counts: Counter[str]) -> str:
    labels = {
        "success": "found",
        "not_found": "not found",
        "empty": "empty",
        "rate_limited": "rate limited",
        "timeout": "timed out",
        "error": "failed",
        "pending": "pending",
    }
    return ". ".join(
        f"{counts[status]:,} {label}" for status, label in labels.items() if counts[status]
    )


def fetch_source_statuses(fetch: AuditRun | None) -> list[SourceStatus]:
    if fetch is None:
        return []
    progress = {
        stage: AuditSourceProgress.model_validate(value)
        for stage, value in (fetch.source_progress or {}).items()
    }
    fallback_time = utc_datetime(fetch.finished_at)
    statuses = []
    for source, stages in OVERVIEW_SOURCE_STAGES.items():
        stage_progress = [progress[stage] for stage in stages if stage in progress]
        if not stage_progress:
            continue
        counts: Counter[str] = Counter()
        completed_times = []
        for stage in stage_progress:
            counts.update(stage.by_status)
            if stage.completed_at is not None:
                completed_times.append(utc_datetime(stage.completed_at))
        statuses.append(
            SourceStatus(
                source=source,
                fetched_at=max(completed_times) if completed_times else fallback_time,
                state=source_state(counts),
                note=source_note(counts),
            )
        )
    return statuses


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
            sources=[],
        )
    ensure_audit_idle(session)

    review_cases = list(
        session.scalars(
            select(ValidationCase).where(
                ValidationCase.dataset_snapshot_id == snapshot.id,
                ValidationCase.queue_eligible.is_(True),
            )
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
    completed_fetch = latest_completed_fetch(session, snapshot.id)

    return ReviewOverview(
        authors=len(review_cases),
        publications=sum(review_case.affected_count for review_case in review_cases),
        authors_audited=authors_audited or 0,
        publications_audited=publications_audited or 0,
        audited_at=utc_datetime(completed_fetch.finished_at) if completed_fetch else None,
        sources=fetch_source_statuses(completed_fetch),
    )
