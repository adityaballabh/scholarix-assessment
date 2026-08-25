import json
import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from merge_review.api.cases import case_responses, filtered_case_rows
from merge_review.api.common import ensure_fetch_idle, latest_snapshot, utc_datetime
from merge_review.api.queue import queue_settings_response
from merge_review.database import get_session
from merge_review.generate_cases import default_review_settings
from merge_review.models import Author, DatasetSnapshot, ReviewSettings, ValidationCase
from merge_review.schemas import (
    EvidenceExport,
    ExportFilters,
    ExportSnapshot,
    QueueScope,
    ValidationCaseResponse,
)

router = APIRouter()

FILENAME_STEM = "merge-review-evidence"


def filename_slug(value: str) -> str:
    """A filename the reviewer can recognise in a downloads folder, ASCII and lowercase."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "case"


def hold_snapshot(session: Session) -> None:
    """Take a shared lock on the snapshot row before reading, and hold it to commit.

    `ensure_fetch_idle` is a point-in-time check, so on its own a fetch could start between it
    and the batched reads below, letting one file mix pre- and post-rebuild rows. `start_fetch`
    already takes `FOR UPDATE` on this row, so a shared lock here makes the two mutually
    exclusive for the milliseconds an export takes. PostgreSQL only; SQLite ignores it, so the
    suite cannot prove this and the interleaving stays untested.
    """
    session.scalars(
        select(DatasetSnapshot)
        .order_by(DatasetSnapshot.imported_at.desc())
        .limit(1)
        .with_for_update(read=True)
    ).all()


def export_document(
    session: Session,
    cases: list[ValidationCaseResponse],
    filters: ExportFilters | None,
) -> EvidenceExport:
    snapshot = latest_snapshot(session)
    if snapshot is None:
        raise HTTPException(404, detail="No dataset imported")
    settings = session.get(ReviewSettings, snapshot.id) or default_review_settings(snapshot.id)
    return EvidenceExport(
        exported_at=datetime.now(UTC),
        dataset_snapshot=ExportSnapshot(
            id=snapshot.id,
            dataset_sha256=snapshot.dataset_sha256,
            imported_at=utc_datetime(snapshot.imported_at),
        ),
        queue_settings=queue_settings_response(settings),
        filters=filters,
        case_count=len(cases),
        cases=cases,
    )


def download(document: EvidenceExport, filename: str) -> Response:
    # Indented rather than the default minified JSON: this file exists to be read. Accented
    # names stay as themselves rather than escaping to \uXXXX.
    body = json.dumps(document.model_dump(mode="json"), indent=2, ensure_ascii=False)
    # Without Content-Disposition the browser renders the JSON instead of saving it.
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/cases/{case_id}/export", response_model=EvidenceExport)
def export_case(case_id: str, session: Session = Depends(get_session)) -> Response:
    hold_snapshot(session)
    ensure_fetch_idle(session)
    row = session.execute(
        select(ValidationCase, Author).join(Author).where(ValidationCase.id == case_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(404, detail="Case not found")
    cases = case_responses(session, [(row[0], row[1])])
    document = export_document(session, cases, filters=None)
    return download(document, f"{FILENAME_STEM}-{filename_slug(cases[0].target.author_slug)}.json")


@router.get("/export", response_model=EvidenceExport)
def export_cases(
    status: str | None = None,
    scope: QueueScope = "active",
    query: str | None = None,
    session: Session = Depends(get_session),
) -> Response:
    """The whole filtered set, deliberately unpaginated.

    The queue list caps at 50 because it is a screen. A file that silently stopped at the
    same boundary would under-report the review state with nothing to say it had.
    """
    hold_snapshot(session)
    ensure_fetch_idle(session)
    rows = filtered_case_rows(session, status, scope, query, None, 0)
    cases = case_responses(session, rows)
    filters = ExportFilters(scope=scope, status=status, query=query)
    document = export_document(session, cases, filters)
    stamp = document.exported_at.strftime("%Y%m%d")
    return download(document, f"{FILENAME_STEM}-{scope}-{stamp}.json")
