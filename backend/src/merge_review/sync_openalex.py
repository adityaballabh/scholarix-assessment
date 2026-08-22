from collections import Counter
from dataclasses import replace
from uuid import UUID

from requests import Session
from sqlalchemy import select
from sqlalchemy.orm import Session as DatabaseSession

from merge_review.config import get_settings
from merge_review.database import SessionFactory, create_schema
from merge_review.models import Author, DatasetSnapshot
from merge_review.source_records import (
    FetchStatus,
    SourceResult,
    completed_counts,
    completed_keys,
    create_http_session,
    request_json,
    store_source_result,
)


def fetch_openalex_author(
    session: Session,
    author_id: str,
    mailto: str | None = None,
) -> SourceResult:
    params = {"mailto": mailto} if mailto else None
    result = request_json(
        session,
        source="openalex",
        entity_type="author",
        entity_key=author_id,
        request_url=f"https://api.openalex.org/authors/{author_id}",
        record_url=f"https://openalex.org/{author_id}",
        params=params,
    )
    if result.fetch_status != FetchStatus.SUCCESS or not isinstance(result.payload, dict):
        return result
    source_record_id = result.payload.get("id")
    return replace(
        result,
        source_record_id=source_record_id if isinstance(source_record_id, str) else author_id,
    )


def sync_openalex_authors(
    session: DatabaseSession,
    http_session: Session,
    snapshot_id: UUID,
    mailto: str | None = None,
    author_ids: list[str] | None = None,
    force: bool = False,
) -> Counter[str]:
    if author_ids is None:
        author_ids = list(
            session.scalars(
                select(Author.source_id)
                .where(Author.dataset_snapshot_id == snapshot_id)
                .order_by(Author.source_id)
            )
        )
    successful_ids = set() if force else completed_keys(session, snapshot_id, "openalex", "author")
    counts = Counter() if force else completed_counts(session, snapshot_id, "openalex", "author")

    for author_id in author_ids:
        if author_id in successful_ids:
            continue

        result = fetch_openalex_author(http_session, author_id, mailto)
        store_source_result(session, snapshot_id, result, preserve_success=force)
        counts[result.fetch_status] += 1

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
            raise RuntimeError("Import a dataset before syncing OpenAlex")
        counts = sync_openalex_authors(session, http_session, snapshot.id, settings.mailto)

    print(f"OpenAlex author records for snapshot {snapshot.id}")
    for status in FetchStatus:
        if counts[status]:
            print(f"{status}: {counts[status]}")


if __name__ == "__main__":
    main()
