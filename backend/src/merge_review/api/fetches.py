from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from merge_review.api.common import (
    current_fetch,
    ensure_fetch_idle,
    last_successful_fetch_at,
    utc_datetime,
)
from merge_review.database import get_session
from merge_review.fetch import run_fetch
from merge_review.models import DatasetSnapshot, FetchRun, User
from merge_review.schemas import FetchRunResponse, FetchSourceProgress
from merge_review.security import (
    READ_METHODS,
    reject_foreign_origin,
    resolve_user,
    session_cookie,
)


def authenticate_fetch(
    request: Request,
    token: str | None = Depends(session_cookie),
    session: Session = Depends(get_session),
) -> User | None:
    if request.method in READ_METHODS:
        return None
    reject_foreign_origin(request)
    if last_successful_fetch_at(session) is None:
        return None
    return resolve_user(token, session)


router = APIRouter(dependencies=[Depends(authenticate_fetch)])


def fetch_response(fetch: FetchRun, last_successful_at: datetime | None) -> FetchRunResponse:
    return FetchRunResponse(
        id=str(fetch.id),
        status=fetch.status,
        current_source=fetch.current_source,
        source_progress={
            source: FetchSourceProgress.model_validate(progress)
            for source, progress in (fetch.source_progress or {}).items()
        },
        started_at=utc_datetime(fetch.started_at),
        finished_at=utc_datetime(fetch.finished_at),
        last_completed_at=utc_datetime(last_successful_at),
        error=fetch.error,
    )


@router.get("/fetches/current", response_model=FetchRunResponse | None)
def get_fetch(session: Session = Depends(get_session)) -> FetchRunResponse | None:
    fetch = current_fetch(session)
    return fetch_response(fetch, last_successful_fetch_at(session)) if fetch else None


@router.post("/fetches", response_model=FetchRunResponse, status_code=202)
def start_fetch(
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> FetchRunResponse:
    snapshot = session.scalar(
        select(DatasetSnapshot)
        .order_by(DatasetSnapshot.imported_at.desc(), DatasetSnapshot.id.desc())
        .limit(1)
        .with_for_update()
    )
    if snapshot is None:
        raise HTTPException(404, detail="No dataset imported")
    ensure_fetch_idle(session)
    fetch = FetchRun(
        dataset_snapshot_id=snapshot.id,
        status="queued",
        source_progress={},
    )
    session.add(fetch)
    session.flush()
    session.refresh(fetch)
    response = fetch_response(fetch, last_successful_fetch_at(session))
    session.commit()
    background_tasks.add_task(run_fetch, fetch.id, snapshot.id)
    return response


@router.post("/fetches/{fetch_id}/abandon", response_model=FetchRunResponse)
def abandon_fetch(
    fetch_id: UUID,
    session: Session = Depends(get_session),
) -> FetchRunResponse:
    snapshot_id = session.scalar(
        select(FetchRun.dataset_snapshot_id).where(FetchRun.id == fetch_id)
    )
    if snapshot_id is None:
        raise HTTPException(404, detail="Fetch not found")
    session.scalar(
        select(DatasetSnapshot).where(DatasetSnapshot.id == snapshot_id).with_for_update()
    )
    ensure_fetch_idle(session)
    fetch = session.scalar(select(FetchRun).where(FetchRun.id == fetch_id).with_for_update())
    if fetch is None:
        raise HTTPException(404, detail="Fetch not found")
    latest = current_fetch(session)
    if latest is None or latest.id != fetch.id:
        raise HTTPException(409, detail="Fetch is no longer current")
    if fetch.status != "failed":
        raise HTTPException(409, detail="Only a failed fetch can be abandoned")
    fetch.status = "abandoned"
    session.commit()
    session.refresh(fetch)
    return fetch_response(fetch, last_successful_fetch_at(session))
