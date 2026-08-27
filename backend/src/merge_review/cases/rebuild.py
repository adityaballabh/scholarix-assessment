from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from merge_review.cases.generate import generate_identity_cases
from merge_review.models import DatasetSnapshot, ReviewSettings, ValidationCase


def rebuild_queue(session: Session, snapshot_id: UUID) -> int:
    session.scalar(
        select(DatasetSnapshot).where(DatasetSnapshot.id == snapshot_id).with_for_update()
    )
    # Materialize every case lock before regeneration changes their order or contents
    session.scalars(
        select(ValidationCase)
        .where(ValidationCase.dataset_snapshot_id == snapshot_id)
        .order_by(ValidationCase.id)
        .with_for_update()
    ).all()
    case_count = generate_identity_cases(session, snapshot_id)
    settings = session.get(ReviewSettings, snapshot_id)
    if settings is None:
        raise RuntimeError("Queue settings disappeared")
    settings.queue_updated_at = datetime.now(UTC)
    return case_count
