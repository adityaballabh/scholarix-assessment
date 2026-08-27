import json
from collections import defaultdict
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from merge_review.api.activity import activity_response
from merge_review.api.case_read import case_responses, filtered_case_rows
from merge_review.api.common import lock_current_snapshot_for_read, utc_datetime
from merge_review.api.queue import queue_settings_response
from merge_review.cases.generate import default_review_settings
from merge_review.cases.naming import normalized_words
from merge_review.database import get_session
from merge_review.models import (
    ActivityEvent,
    Author,
    DatasetSnapshot,
    ReviewSettings,
    ValidationCase,
)
from merge_review.schemas import (
    EvidenceExport,
    ExportedCase,
    ExportFilters,
    ExportSnapshot,
    QueueScope,
    ValidationCaseResponse,
)

router = APIRouter()

FILENAME_STEM = "evidence"


def filename_slug(value: str) -> str:
    return "-".join(normalized_words(value)) or "case"


def with_history(
    session: Session,
    cases: list[ValidationCaseResponse],
) -> list[ExportedCase]:
    if not cases:
        return []
    events: dict[str, list[ActivityEvent]] = defaultdict(list)
    for event in session.scalars(
        select(ActivityEvent)
        .where(ActivityEvent.case_id.in_([case.id for case in cases]))
        .order_by(ActivityEvent.created_at, ActivityEvent.id)
    ):
        events[event.case_id].append(event)
    return [
        ExportedCase(
            **case.model_dump(),
            history=[activity_response(event) for event in events[case.id]],
        )
        for case in cases
    ]


def export_document(
    session: Session,
    snapshot: DatasetSnapshot,
    cases: list[ValidationCaseResponse],
    filters: ExportFilters | None,
) -> EvidenceExport:
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
        cases=with_history(session, cases),
    )


def download(document: EvidenceExport, filename: str) -> Response:
    body = json.dumps(document.model_dump(mode="json"), indent=2, ensure_ascii=False)
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/cases/{case_id}/export", response_model=EvidenceExport)
def export_case(case_id: str, session: Session = Depends(get_session)) -> Response:
    snapshot = lock_current_snapshot_for_read(session)
    if snapshot is None:
        raise HTTPException(404, detail="Case not found")
    row = session.execute(
        select(ValidationCase, Author)
        .join(Author)
        .where(
            ValidationCase.id == case_id,
            ValidationCase.dataset_snapshot_id == snapshot.id,
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(404, detail="Case not found")
    cases = case_responses(session, [(row[0], row[1])])
    document = export_document(session, snapshot, cases, filters=None)
    return download(document, f"{FILENAME_STEM}-{filename_slug(cases[0].target.author_name)}.json")


@router.get("/export", response_model=EvidenceExport)
def export_cases(
    status: str | None = None,
    scope: QueueScope = "active",
    query: str | None = None,
    session: Session = Depends(get_session),
) -> Response:
    snapshot = lock_current_snapshot_for_read(session)
    if snapshot is None:
        raise HTTPException(404, detail="No dataset imported")
    rows = filtered_case_rows(
        session,
        snapshot_id=snapshot.id,
        status=status,
        scope=scope,
        query=query,
        limit=None,
        offset=0,
    )
    cases = case_responses(session, rows)
    filters = ExportFilters(scope=scope, status=status, query=query)
    document = export_document(session, snapshot, cases, filters)
    stamp = document.exported_at.strftime("%Y%m%d")
    return download(document, f"{FILENAME_STEM}-{scope}-{stamp}.json")
