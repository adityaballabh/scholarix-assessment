from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from merge_review.generate_cases import generate_identity_cases
from merge_review.models import DatasetSnapshot, ValidationCase


def run_audit(session: Session, snapshot_id: UUID) -> dict[str, int]:
    session.scalar(
        select(DatasetSnapshot).where(DatasetSnapshot.id == snapshot_id).with_for_update()
    )
    session.scalars(
        select(ValidationCase)
        .where(ValidationCase.dataset_snapshot_id == snapshot_id)
        .order_by(ValidationCase.id)
        .with_for_update()
    ).all()
    return generate_identity_cases(session, snapshot_id)
