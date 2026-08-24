import time
from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select

from merge_review.audit_service import run_audit
from merge_review.config import get_settings
from merge_review.database import SessionFactory
from merge_review.models import AuditRun, Author
from merge_review.source_records import (
    FetchStatus,
    create_http_session,
    uncached_http_session,
)
from merge_review.sync_openalex import sync_openalex_authors
from merge_review.sync_sources import (
    snapshot_dois,
    sync_openalex_author_publications,
    sync_openalex_publication_records,
    sync_orcid_records,
    sync_semantic_scholar_records,
)


class AuditProgressReporter:
    def __init__(self, audit_id: UUID) -> None:
        self.audit_id = audit_id
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
            audit = session.get(AuditRun, self.audit_id)
            if audit is None:
                return
            progress = dict(audit.source_progress or {})
            source_progress: dict[str, object] = {
                "completed": completed,
                "total": total,
                "by_status": {str(status): count for status, count in counts.items() if count},
            }
            if completed == total:
                source_progress["completed_at"] = datetime.now(UTC).isoformat()
            progress[source] = source_progress
            audit.current_source = source
            audit.source_progress = progress
        self.last_write = now


def update_audit(
    audit_id: UUID,
    status: str,
    *,
    error: str | None = None,
) -> None:
    with SessionFactory.begin() as session:
        audit = session.get(AuditRun, audit_id)
        if audit is None:
            return
        audit.status = status
        audit.error = error
        if status == "running":
            audit.started_at = datetime.now(UTC)
        if status in {"complete", "failed"}:
            audit.finished_at = datetime.now(UTC)
            audit.current_source = None


def fail_interrupted_audits() -> None:
    with SessionFactory.begin() as session:
        audits = session.scalars(select(AuditRun).where(AuditRun.status.in_(["queued", "running"])))
        finished_at = datetime.now(UTC)
        for audit in audits:
            audit.status = "failed"
            audit.finished_at = finished_at
            audit.current_source = None
            audit.error = "Audit interrupted by server restart"


def run_full_audit(audit_id: UUID, snapshot_id: UUID) -> None:
    reporter = AuditProgressReporter(audit_id)
    settings = get_settings()
    try:
        update_audit(audit_id, "running")
        http_context = (
            create_http_session() if settings.audit_use_cache else uncached_http_session()
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
            run_audit(session, snapshot_id)
            reporter(
                "case_generation",
                author_count,
                author_count,
                Counter({FetchStatus.SUCCESS: author_count}),
            )
            audit = session.get(AuditRun, audit_id)
            if audit is None:
                raise RuntimeError("Audit run disappeared")
            audit.status = "complete"
            audit.finished_at = datetime.now(UTC)
            audit.current_source = None
    except Exception as error:
        update_audit(audit_id, "failed", error=str(error)[:500])
