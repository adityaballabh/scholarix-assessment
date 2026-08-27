from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from merge_review.api.common import ensure_fetch_idle, latest_snapshot, utc_datetime
from merge_review.cases.generate import default_review_settings, get_or_create_review_settings
from merge_review.cases.rebuild import rebuild_queue
from merge_review.database import get_session
from merge_review.models import DatasetSnapshot, ReviewSettings
from merge_review.schemas import QueueRebuildResponse, QueueSettingsResponse, QueueSettingsUpdate

router = APIRouter()


def queue_settings_response(settings: ReviewSettings) -> QueueSettingsResponse:
    return QueueSettingsResponse(
        max_top_candidate_share=settings.max_top_candidate_share,
        weights=settings.priority_weights,
        version=settings.version,
        updated_at=utc_datetime(settings.updated_at),
    )


@router.get("/queue/settings", response_model=QueueSettingsResponse)
def get_queue_settings(session: Session = Depends(get_session)) -> QueueSettingsResponse:
    snapshot = latest_snapshot(session)
    if snapshot is None:
        raise HTTPException(404, detail="No dataset imported")
    ensure_fetch_idle(session)
    settings = session.get(ReviewSettings, snapshot.id) or default_review_settings(snapshot.id)
    return queue_settings_response(settings)


@router.put("/queue/settings", response_model=QueueSettingsResponse)
def update_queue_settings(
    request: QueueSettingsUpdate,
    session: Session = Depends(get_session),
) -> QueueSettingsResponse:
    snapshot = latest_snapshot(session)
    if snapshot is None:
        raise HTTPException(404, detail="No dataset imported")
    session.scalar(
        select(DatasetSnapshot).where(DatasetSnapshot.id == snapshot.id).with_for_update()
    )
    ensure_fetch_idle(session)
    settings = session.scalar(
        select(ReviewSettings)
        .where(ReviewSettings.dataset_snapshot_id == snapshot.id)
        .with_for_update()
    )
    if settings is None:
        settings = get_or_create_review_settings(session, snapshot.id)
    if settings.version != request.expected_version:
        raise HTTPException(409, detail={"current_version": settings.version})

    settings.max_top_candidate_share = request.max_top_candidate_share
    settings.priority_weights = request.weights.model_dump()
    settings.version += 1
    session.commit()
    session.refresh(settings)
    return queue_settings_response(settings)


@router.post("/queue/rebuild", response_model=QueueRebuildResponse)
def rebuild_review_queue(session: Session = Depends(get_session)) -> QueueRebuildResponse:
    snapshot = latest_snapshot(session)
    if snapshot is None:
        raise HTTPException(404, detail="No dataset imported")
    session.scalar(
        select(DatasetSnapshot).where(DatasetSnapshot.id == snapshot.id).with_for_update()
    )
    ensure_fetch_idle(session)
    cases = rebuild_queue(session, snapshot.id)
    settings = get_or_create_review_settings(session, snapshot.id)
    response = QueueRebuildResponse(config_version=settings.version, cases=cases)
    session.commit()
    return response
