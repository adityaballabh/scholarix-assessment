import time
from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select

from merge_review.config import get_settings
from merge_review.database import SessionFactory
from merge_review.models import Author, FetchRun
from merge_review.rebuild_queue import rebuild_queue
from merge_review.sources.common import (
    FetchStatus,
    create_http_session,
    uncached_http_session,
)
from merge_review.sources.openalex import (
    sync_openalex_author_publications,
    sync_openalex_authors,
    sync_openalex_publication_records,
)
from merge_review.sources.orcid import sync_orcid_records
from merge_review.sources.semantic_scholar import sync_semantic_scholar_records
from merge_review.sources.sync import snapshot_dois


class FetchProgressReporter:
    def __init__(self, fetch_id: UUID) -> None:
        self.fetch_id = fetch_id
        self.last_write = 0.0

    def start(self, source: str, total: int) -> None:
        self.update(source, 0, total, Counter(), force=True)

    def __call__(
        self,
        source: str,
        completed: int,
        total: int,
        counts: Counter[str],
    ) -> None:
        self.update(source, completed, total, counts, force=completed == total)

    def update(
        self,
        source: str,
        completed: int,
        total: int,
        counts: Counter[str],
        force: bool,
    ) -> None:
        now = time.monotonic()
        if not force and now - self.last_write < 0.5:
            return
        with SessionFactory.begin() as session:
            fetch = session.get(FetchRun, self.fetch_id)
            if fetch is None:
                return
            progress = dict(fetch.source_progress or {})
            source_progress: dict[str, object] = {
                "completed": completed,
                "total": total,
                "by_status": {str(status): count for status, count in counts.items() if count},
            }
            if completed == total:
                source_progress["completed_at"] = datetime.now(UTC).isoformat()
            progress[source] = source_progress
            fetch.current_source = source
            fetch.source_progress = progress
        self.last_write = now


def update_fetch(
    fetch_id: UUID,
    status: str,
    *,
    error: str | None = None,
) -> None:
    with SessionFactory.begin() as session:
        fetch = session.get(FetchRun, fetch_id)
        if fetch is None:
            return
        fetch.status = status
        fetch.error = error
        if status == "running":
            fetch.started_at = datetime.now(UTC)
        if status in {"complete", "failed"}:
            fetch.finished_at = datetime.now(UTC)
            fetch.current_source = None


def fail_interrupted_fetches() -> None:
    with SessionFactory.begin() as session:
        fetches = session.scalars(
            select(FetchRun).where(FetchRun.status.in_(["queued", "running"]))
        )
        finished_at = datetime.now(UTC)
        for fetch in fetches:
            fetch.status = "failed"
            fetch.finished_at = finished_at
            fetch.current_source = None
            fetch.error = "Fetch interrupted by server restart"


def run_fetch(fetch_id: UUID, snapshot_id: UUID) -> None:
    reporter = FetchProgressReporter(fetch_id)
    settings = get_settings()
    try:
        update_fetch(fetch_id, "running")
        http_context = (
            create_http_session() if settings.fetch_use_cache else uncached_http_session()
        )
        with SessionFactory.begin() as session, http_context as http_session:
            author_count = (
                session.scalar(
                    select(func.count(Author.id)).where(Author.dataset_snapshot_id == snapshot_id)
                )
                or 0
            )
            orcid_count = (
                session.scalar(
                    select(func.count(Author.id)).where(
                        Author.dataset_snapshot_id == snapshot_id,
                        Author.orcid_id.is_not(None),
                    )
                )
                or 0
            )
            dois = snapshot_dois(session, snapshot_id)

            reporter.start("openalex_authors", author_count)
            sync_openalex_authors(
                session,
                http_session,
                snapshot_id,
                settings.mailto,
                force=True,
                progress=reporter,
            )
            reporter.start("openalex_author_publications", author_count)
            sync_openalex_author_publications(
                session,
                http_session,
                snapshot_id,
                settings.mailto,
                force=True,
                progress=reporter,
            )
            reporter.start("openalex_publications", len(dois))
            sync_openalex_publication_records(
                session,
                http_session,
                snapshot_id,
                dois,
                settings.mailto,
                force=True,
                progress=reporter,
            )
            reporter.start("orcid", orcid_count)
            sync_orcid_records(
                session,
                http_session,
                snapshot_id,
                force=True,
                progress=reporter,
            )
            reporter.start("semantic_scholar", len(dois))
            sync_semantic_scholar_records(
                session,
                http_session,
                snapshot_id,
                dois,
                force=True,
                progress=reporter,
            )

            reporter.start("case_generation", author_count)
            rebuild_queue(session, snapshot_id)
            reporter(
                "case_generation",
                author_count,
                author_count,
                Counter({FetchStatus.SUCCESS: author_count}),
            )
            fetch = session.get(FetchRun, fetch_id)
            if fetch is None:
                raise RuntimeError("Fetch run disappeared")
            fetch.status = "complete"
            fetch.finished_at = datetime.now(UTC)
            fetch.current_source = None
    except Exception as error:
        update_fetch(fetch_id, "failed", error=str(error)[:500])
