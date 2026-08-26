from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from merge_review.api.common import (
    ensure_fetch_idle,
    latest_completed_fetch,
    latest_snapshot,
    utc_datetime,
)
from merge_review.database import get_session
from merge_review.models import Author, FetchRun, PublicationRecord, ReviewSettings, ValidationCase
from merge_review.schemas import FetchSourceProgress, ReviewOverview, SourceStatus

router = APIRouter()
OVERVIEW_SOURCE_STAGES = {
    "openalex": (
        "openalex_authors",
        "openalex_author_publications",
        "openalex_publications",
    ),
    "orcid": ("orcid",),
    "semantic_scholar": ("semantic_scholar",),
}


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


def fetch_source_statuses(fetch: FetchRun | None) -> list[SourceStatus]:
    if fetch is None:
        return []
    progress = {
        stage: FetchSourceProgress.model_validate(value)
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
            flagged_authors=0,
            affected_publications=0,
            total_authors=0,
            total_publications=0,
            queue_updated_at=None,
            sources=[],
        )
    ensure_fetch_idle(session)

    review_cases = list(
        session.scalars(
            select(ValidationCase).where(
                ValidationCase.dataset_snapshot_id == snapshot.id,
                ValidationCase.queue_eligible.is_(True),
            )
        )
    )
    total_authors = session.scalar(
        select(func.count(Author.id)).where(Author.dataset_snapshot_id == snapshot.id)
    )
    total_publications = session.scalar(
        select(func.count(PublicationRecord.id))
        .join(Author)
        .where(Author.dataset_snapshot_id == snapshot.id)
    )
    completed_fetch = latest_completed_fetch(session, snapshot.id)
    settings = session.get(ReviewSettings, snapshot.id)

    return ReviewOverview(
        flagged_authors=len(review_cases),
        affected_publications=sum(review_case.affected_count for review_case in review_cases),
        total_authors=total_authors or 0,
        total_publications=total_publications or 0,
        queue_updated_at=utc_datetime(settings.queue_updated_at) if settings else None,
        sources=fetch_source_statuses(completed_fetch),
    )
