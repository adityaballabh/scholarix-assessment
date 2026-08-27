from collections import Counter
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session as DatabaseSession

from merge_review.models import Author, PublicationRecord


def snapshot_dois(session: DatabaseSession, snapshot_id: UUID) -> list[str]:
    return list(
        session.scalars(
            select(PublicationRecord.normalized_doi)
            .join(Author)
            .where(
                Author.dataset_snapshot_id == snapshot_id,
                PublicationRecord.normalized_doi.is_not(None),
            )
            .distinct()
            .order_by(PublicationRecord.normalized_doi)
        )
    )


def merge_counts(total: Counter[str], source: str, counts: Counter[str]) -> None:
    for status, count in counts.items():
        total[f"{source}:{status}"] += count
