from collections import Counter
from dataclasses import replace
from typing import Any
from uuid import UUID

from requests import Session
from sqlalchemy import select
from sqlalchemy.orm import Session as DatabaseSession

from merge_review.config import get_settings
from merge_review.database import SessionFactory, create_schema
from merge_review.import_dataset import normalize_doi
from merge_review.models import Author, DatasetSnapshot
from merge_review.sources.common import (
    FetchStatus,
    ProgressCallback,
    SourceResult,
    batches,
    completed_counts,
    completed_keys,
    create_http_session,
    expand_result,
    request_json,
    store_source_result,
)


def fetch_openalex_author(
    http_session: Session,
    author_id: str,
    mailto: str | None = None,
) -> SourceResult:
    params = {"mailto": mailto} if mailto else None
    result = request_json(
        http_session,
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
    progress: ProgressCallback | None = None,
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

    total = len(author_ids)
    completed = 0
    for author_id in author_ids:
        if author_id in successful_ids:
            continue

        result = fetch_openalex_author(http_session, author_id, mailto)
        record = store_source_result(session, snapshot_id, result, refetching=force)
        counts[record.fetch_status] += 1
        completed += 1
        if progress:
            progress("openalex_authors", completed, total, counts)

    return counts


def fetch_openalex_batch(
    http_session: Session,
    dois: list[str],
    mailto: str | None,
) -> tuple[SourceResult, dict[str, dict[str, Any]]]:
    results = []
    cursor = "*"
    last_result: SourceResult | None = None

    while cursor:
        params = {
            "filter": "doi:" + "|".join(dois),
            "per_page": 100,
            "cursor": cursor,
        }
        if mailto:
            params["mailto"] = mailto
        last_result = request_json(
            http_session,
            source="openalex",
            entity_type="publication_batch",
            entity_key=dois[0],
            request_url="https://api.openalex.org/works",
            params=params,
        )
        if last_result.fetch_status != FetchStatus.SUCCESS:
            return last_result, {}
        payload = last_result.payload
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            return replace(
                last_result,
                fetch_status=FetchStatus.ERROR,
                error="OpenAlex response contained no results list",
                payload=None,
            ), {}
        results.extend(payload["results"])
        meta = payload.get("meta") or {}
        cursor = meta.get("next_cursor")

    publications = {}
    for publication in results:
        if not isinstance(publication, dict):
            continue
        doi = normalize_doi(publication.get("doi"))
        if doi:
            publications[doi] = publication
    return last_result, publications


def sync_openalex_publication_records(
    session: DatabaseSession,
    http_session: Session,
    snapshot_id: UUID,
    dois: list[str],
    mailto: str | None,
    force: bool = False,
    progress: ProgressCallback | None = None,
) -> Counter[str]:
    done = set() if force else completed_keys(session, snapshot_id, "openalex", "publication")
    pending = [doi for doi in dois if doi not in done]
    counts = (
        Counter() if force else completed_counts(session, snapshot_id, "openalex", "publication")
    )

    total = len(pending)
    completed = 0
    for batch in batches(pending, 100):
        batch_result, publications = fetch_openalex_batch(http_session, batch, mailto)
        for doi in batch:
            publication = publications.get(doi)
            if publication is not None:
                record_id = publication.get("id")
                result = expand_result(
                    batch_result,
                    "publication",
                    doi,
                    record_id if isinstance(record_id, str) else f"https://doi.org/{doi}",
                    payload=publication,
                    source_record_id=record_id if isinstance(record_id, str) else doi,
                    status=FetchStatus.SUCCESS,
                )
            elif batch_result.fetch_status == FetchStatus.SUCCESS:
                result = expand_result(
                    batch_result,
                    "publication",
                    doi,
                    f"https://doi.org/{doi}",
                    status=FetchStatus.NOT_FOUND,
                    error="No OpenAlex work matched this DOI",
                )
            else:
                result = expand_result(
                    batch_result,
                    "publication",
                    doi,
                    f"https://doi.org/{doi}",
                )
            record = store_source_result(session, snapshot_id, result, refetching=force)
            counts[record.fetch_status] += 1
            completed += 1
            if progress:
                progress("openalex_publications", completed, total, counts)
    return counts


def fetch_openalex_author_publications(
    http_session: Session,
    author_id: str,
    mailto: str | None,
) -> SourceResult:
    dois = set()
    cursor = "*"
    total = 0
    last_result: SourceResult | None = None

    while cursor:
        params = {
            "filter": f"author.id:{author_id}",
            "select": "doi",
            "per_page": 100,
            "cursor": cursor,
        }
        if mailto:
            params["mailto"] = mailto
        last_result = request_json(
            http_session,
            source="openalex",
            entity_type="author_publications",
            entity_key=author_id,
            request_url="https://api.openalex.org/works",
            record_url=f"https://openalex.org/{author_id}",
            params=params,
        )
        if last_result.fetch_status != FetchStatus.SUCCESS:
            return last_result
        payload = last_result.payload
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            return replace(
                last_result,
                fetch_status=FetchStatus.ERROR,
                error="OpenAlex response contained no results list",
                payload=None,
            )
        for publication in payload["results"]:
            if isinstance(publication, dict):
                doi = normalize_doi(publication.get("doi"))
                if doi:
                    dois.add(doi)
        meta = payload.get("meta") or {}
        total = meta.get("count", total)
        cursor = meta.get("next_cursor")

    return replace(
        last_result,
        source_record_id=author_id,
        payload={"source_count": total, "dois": sorted(dois)},
    )


def sync_openalex_author_publications(
    session: DatabaseSession,
    http_session: Session,
    snapshot_id: UUID,
    mailto: str | None,
    author_ids: list[str] | None = None,
    force: bool = False,
    progress: ProgressCallback | None = None,
) -> Counter[str]:
    if author_ids is None:
        author_ids = list(
            session.scalars(
                select(Author.source_id)
                .where(Author.dataset_snapshot_id == snapshot_id)
                .order_by(Author.source_id)
            )
        )
    done = (
        set() if force else completed_keys(session, snapshot_id, "openalex", "author_publications")
    )
    counts = (
        Counter()
        if force
        else completed_counts(session, snapshot_id, "openalex", "author_publications")
    )

    total = len(author_ids)
    completed = 0
    for author_id in author_ids:
        if author_id in done:
            continue
        result = fetch_openalex_author_publications(http_session, author_id, mailto)
        record = store_source_result(session, snapshot_id, result, refetching=force)
        counts[record.fetch_status] += 1
        completed += 1
        if progress:
            progress("openalex_author_publications", completed, total, counts)
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
