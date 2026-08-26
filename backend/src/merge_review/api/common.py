from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from merge_review.models import DatasetSnapshot, FetchRun, ValidationCase

ACTIVE_FETCH_STATUSES = {"queued", "running"}


def latest_snapshot(session: Session) -> DatasetSnapshot | None:
    return session.scalar(
        select(DatasetSnapshot).order_by(DatasetSnapshot.imported_at.desc()).limit(1)
    )


def current_fetch(session: Session) -> FetchRun | None:
    return session.scalar(
        select(FetchRun).order_by(FetchRun.created_at.desc(), FetchRun.id.desc()).limit(1)
    )


def last_completed_at(session: Session) -> datetime | None:
    return session.scalar(
        select(func.max(FetchRun.finished_at)).where(FetchRun.status == "complete")
    )


def latest_completed_fetch(session: Session, snapshot_id: UUID) -> FetchRun | None:
    return session.scalar(
        select(FetchRun)
        .where(
            FetchRun.dataset_snapshot_id == snapshot_id,
            FetchRun.status == "complete",
        )
        .order_by(FetchRun.finished_at.desc(), FetchRun.id.desc())
        .limit(1)
    )


def ensure_fetch_idle(session: Session) -> None:
    fetch = session.scalar(
        select(FetchRun)
        .where(FetchRun.status.in_(ACTIVE_FETCH_STATUSES))
        .order_by(FetchRun.created_at.desc())
        .limit(1)
    )
    if fetch is not None:
        raise HTTPException(423, detail="Fetch in progress")


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
