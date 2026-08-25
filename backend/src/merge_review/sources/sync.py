from collections import Counter
from uuid import UUID

from requests import Session
from sqlalchemy import select
from sqlalchemy.orm import Session as DatabaseSession

from merge_review.config import get_settings
from merge_review.database import SessionFactory, create_schema
from merge_review.models import Author, DatasetSnapshot, PublicationRecord
from merge_review.sources.common import create_http_session
from merge_review.sources.openalex import (
    sync_openalex_author_publications,
    sync_openalex_authors,
    sync_openalex_publication_records,
)
from merge_review.sources.orcid import sync_orcid_records
from merge_review.sources.semantic_scholar import sync_semantic_scholar_records


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


def sync_all_sources(
    session: DatabaseSession,
    http_session: Session,
    snapshot_id: UUID,
    mailto: str | None,
) -> Counter[str]:
    counts: Counter[str] = Counter()
    dois = snapshot_dois(session, snapshot_id)
    merge_counts(
        counts,
        "openalex_authors",
        sync_openalex_authors(session, http_session, snapshot_id, mailto),
    )
    merge_counts(
        counts,
        "openalex_author_publications",
        sync_openalex_author_publications(session, http_session, snapshot_id, mailto),
    )
    merge_counts(
        counts,
        "openalex_publications",
        sync_openalex_publication_records(session, http_session, snapshot_id, dois, mailto),
    )
    merge_counts(
        counts,
        "orcid",
        sync_orcid_records(session, http_session, snapshot_id),
    )
    merge_counts(
        counts,
        "semantic_scholar",
        sync_semantic_scholar_records(session, http_session, snapshot_id, dois),
    )
    return counts


def main() -> None:
    create_schema()
    settings = get_settings()
    http_session = create_http_session()

    with SessionFactory.begin() as session:
        snapshot = session.scalar(
            select(DatasetSnapshot).order_by(DatasetSnapshot.imported_at.desc()).limit(1)
        )
        if snapshot is None:
            raise RuntimeError("Import a dataset before syncing sources")
        counts = sync_all_sources(session, http_session, snapshot.id, settings.mailto)

    print(f"Source records for snapshot {snapshot.id}")
    for name, count in sorted(counts.items()):
        print(f"{name}: {count}")


if __name__ == "__main__":
    main()
