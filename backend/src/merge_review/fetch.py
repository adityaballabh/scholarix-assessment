import logging
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from requests_cache import CachedSession
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from merge_review.cases.rebuild import rebuild_queue
from merge_review.config import get_settings
from merge_review.database import SessionFactory
from merge_review.models import Author, FetchRun
from merge_review.sources.common import (
    FetchStatus,
    SourceResult,
    http_session_context,
)
from merge_review.sources.openalex import (
    sync_openalex_author_publications,
    sync_openalex_authors,
    sync_openalex_publication_records,
)
from merge_review.sources.orcid import sync_orcid_records
from merge_review.sources.semantic_scholar import (
    fetch_semantic_scholar_records,
    store_semantic_scholar_records,
)
from merge_review.sources.sync import snapshot_dois

logger = logging.getLogger(__name__)


class FetchProgressReporter:
    # Progress writes lock the fetch row and throttle independently per source

    def __init__(self, fetch_id: UUID) -> None:
        self.fetch_id = fetch_id
        self.last_write: dict[str, float] = {}

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
        if not force and now - self.last_write.get(source, 0.0) < 0.5:
            return
        with SessionFactory.begin() as session:
            fetch = session.scalar(
                select(FetchRun).where(FetchRun.id == self.fetch_id).with_for_update()
            )
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
        self.last_write[source] = now


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


@dataclass(frozen=True)
class FetchScope:
    author_count: int
    orcid_count: int
    dois: list[str]


def fetch_scope(session: Session, snapshot_id: UUID) -> FetchScope:
    def author_count(*conditions) -> int:
        return (
            session.scalar(
                select(func.count(Author.id)).where(
                    Author.dataset_snapshot_id == snapshot_id, *conditions
                )
            )
            or 0
        )

    return FetchScope(
        author_count=author_count(),
        orcid_count=author_count(Author.orcid_id.is_not(None)),
        dois=snapshot_dois(session, snapshot_id),
    )


def sync_openalex_and_orcid(
    session: Session,
    http_session: CachedSession,
    snapshot_id: UUID,
    scope: FetchScope,
    mailto: str | None,
    reporter: FetchProgressReporter,
) -> None:
    reporter.start("openalex_authors", scope.author_count)
    sync_openalex_authors(session, http_session, snapshot_id, mailto, force=True, progress=reporter)
    reporter.start("openalex_author_publications", scope.author_count)
    sync_openalex_author_publications(
        session, http_session, snapshot_id, mailto, force=True, progress=reporter
    )
    reporter.start("openalex_publications", len(scope.dois))
    sync_openalex_publication_records(
        session, http_session, snapshot_id, scope.dois, mailto, force=True, progress=reporter
    )
    reporter.start("orcid", scope.orcid_count)
    sync_orcid_records(session, http_session, snapshot_id, force=True, progress=reporter)


def store_semantic_scholar(
    session: Session,
    snapshot_id: UUID,
    results: list[SourceResult],
    reporter: FetchProgressReporter,
) -> None:
    stored = store_semantic_scholar_records(session, snapshot_id, results, force=True)
    reporter("semantic_scholar", len(results), len(results), stored)


def rebuild_and_report(
    session: Session,
    snapshot_id: UUID,
    author_count: int,
    reporter: FetchProgressReporter,
) -> None:
    reporter.start("case_generation", author_count)
    rebuild_queue(session, snapshot_id)
    reporter(
        "case_generation",
        author_count,
        author_count,
        Counter({FetchStatus.SUCCESS: author_count}),
    )


def mark_fetch_complete(session: Session, fetch_id: UUID) -> None:
    fetch = session.get(FetchRun, fetch_id)
    if fetch is None:
        raise RuntimeError("Fetch run disappeared")
    fetch.status = "complete"
    fetch.finished_at = datetime.now(UTC)
    fetch.current_source = None


def run_fetch(fetch_id: UUID, snapshot_id: UUID) -> None:
    reporter = FetchProgressReporter(fetch_id)
    settings = get_settings()
    try:
        update_fetch(fetch_id, "running")
        http_context = http_session_context(settings.fetch_use_cache)
        with SessionFactory.begin() as session, http_context as http_session:
            scope = fetch_scope(session, snapshot_id)

            def fetch_semantic_scholar() -> list[SourceResult]:
                with http_session_context(settings.fetch_use_cache) as worker_http:
                    return fetch_semantic_scholar_records(worker_http, scope.dois, reporter)

            reporter.start("semantic_scholar", len(scope.dois))
            with ThreadPoolExecutor(max_workers=1) as pool:
                semantic_scholar_future = pool.submit(fetch_semantic_scholar)
                sync_openalex_and_orcid(
                    session, http_session, snapshot_id, scope, settings.mailto, reporter
                )
                # Propagate worker failures before the transaction commits
                results = semantic_scholar_future.result()

            store_semantic_scholar(session, snapshot_id, results, reporter)
            rebuild_and_report(session, snapshot_id, scope.author_count, reporter)
            mark_fetch_complete(session, fetch_id)
    except Exception as error:
        logger.exception("Fetch %s failed", fetch_id)
        update_fetch(fetch_id, "failed", error=str(error)[:500])
