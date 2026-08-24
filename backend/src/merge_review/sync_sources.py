import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import replace
from itertools import islice
from typing import Any
from uuid import UUID

from requests import Session
from sqlalchemy import select
from sqlalchemy.orm import Session as DatabaseSession

from merge_review.config import get_settings
from merge_review.database import SessionFactory, create_schema
from merge_review.import_dataset import normalize_doi
from merge_review.models import Author, DatasetSnapshot, PublicationRecord
from merge_review.source_records import (
    FetchStatus,
    ProgressCallback,
    SourceResult,
    completed_counts,
    completed_keys,
    create_http_session,
    request_json,
    store_source_result,
)
from merge_review.sync_openalex import sync_openalex_authors


def batches(values: Iterable[str], size: int) -> Iterable[list[str]]:
    iterator = iter(values)
    while batch := list(islice(iterator, size)):
        yield batch


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


def expand_result(
    result: SourceResult,
    entity_type: str,
    entity_key: str,
    url: str,
    payload: dict[str, Any] | None = None,
    source_record_id: str | None = None,
    status: FetchStatus | None = None,
    error: str | None = None,
) -> SourceResult:
    return replace(
        result,
        entity_type=entity_type,
        entity_key=entity_key,
        url=url,
        source_record_id=source_record_id,
        fetch_status=status or result.fetch_status,
        error=error,
        payload=payload,
    )


def sync_orcid_records(
    session: DatabaseSession,
    http_session: Session,
    snapshot_id: UUID,
    orcid_ids: list[str] | None = None,
    force: bool = False,
    progress: ProgressCallback | None = None,
) -> Counter[str]:
    if orcid_ids is None:
        orcid_ids = list(
            session.scalars(
                select(Author.orcid_id)
                .where(Author.dataset_snapshot_id == snapshot_id, Author.orcid_id.is_not(None))
                .distinct()
                .order_by(Author.orcid_id)
            )
        )
    done = set() if force else completed_keys(session, snapshot_id, "orcid", "author")
    counts = Counter() if force else completed_counts(session, snapshot_id, "orcid", "author")

    total = len(orcid_ids)
    completed = 0
    for orcid_id in orcid_ids:
        if orcid_id in done:
            continue
        url = f"https://orcid.org/{orcid_id}"
        result = request_json(
            http_session,
            source="orcid",
            entity_type="author",
            entity_key=orcid_id,
            request_url=f"https://pub.orcid.org/v3.0/{orcid_id}/record",
            record_url=url,
            headers={"Accept": "application/json"},
        )
        if result.fetch_status == FetchStatus.SUCCESS:
            result = replace(result, source_record_id=orcid_id)
        record = store_source_result(session, snapshot_id, result, preserve_success=force)
        counts[record.fetch_status] += 1
        completed += 1
        if progress:
            progress("orcid", completed, total, counts)
    return counts


def sync_semantic_scholar_records(
    session: DatabaseSession,
    http_session: Session,
    snapshot_id: UUID,
    dois: list[str],
    force: bool = False,
    progress: ProgressCallback | None = None,
) -> Counter[str]:
    done = (
        set() if force else completed_keys(session, snapshot_id, "semantic_scholar", "publication")
    )
    pending = [doi for doi in dois if doi not in done]
    counts = (
        Counter()
        if force
        else completed_counts(session, snapshot_id, "semantic_scholar", "publication")
    )

    total = len(pending)
    completed = 0
    for batch in batches(pending, 500):
        for attempt in range(4):
            time.sleep(5 * attempt)
            batch_result = request_json(
                http_session,
                source="semantic_scholar",
                entity_type="publication_batch",
                entity_key=batch[0],
                request_url="https://api.semanticscholar.org/graph/v1/paper/batch",
                method="POST",
                params={"fields": "externalIds,title,year,authors.authorId,authors.name"},
                json={"ids": [f"DOI:{doi}" for doi in batch]},
            )
            if batch_result.fetch_status != FetchStatus.RATE_LIMITED:
                break
        payload = batch_result.payload
        if batch_result.fetch_status == FetchStatus.SUCCESS and (
            not isinstance(payload, list) or len(payload) != len(batch)
        ):
            batch_result = replace(
                batch_result,
                fetch_status=FetchStatus.ERROR,
                error="Response did not align with the requested DOI batch",
                payload=None,
            )

        for index, doi in enumerate(batch):
            url = f"https://www.semanticscholar.org/paper/DOI:{doi}"
            publication = (
                batch_result.payload[index]
                if batch_result.fetch_status == FetchStatus.SUCCESS
                else None
            )
            valid_publication = (
                isinstance(publication, dict)
                and isinstance(publication.get("paperId"), str)
                and bool(publication["paperId"])
                and isinstance(publication.get("authors"), list)
                and all(isinstance(author, dict) for author in publication["authors"])
            )
            if valid_publication:
                record_id = publication.get("paperId")
                result = expand_result(
                    batch_result,
                    "publication",
                    doi,
                    url,
                    payload=publication,
                    source_record_id=record_id if isinstance(record_id, str) else doi,
                    status=FetchStatus.SUCCESS,
                )
            elif batch_result.fetch_status == FetchStatus.SUCCESS and publication is None:
                result = expand_result(
                    batch_result,
                    "publication",
                    doi,
                    url,
                    status=FetchStatus.NOT_FOUND,
                    error="No Semantic Scholar paper matched this DOI",
                )
            elif batch_result.fetch_status == FetchStatus.SUCCESS:
                result = expand_result(
                    batch_result,
                    "publication",
                    doi,
                    url,
                    status=FetchStatus.ERROR,
                    error="Semantic Scholar returned a malformed paper record",
                )
            else:
                result = expand_result(batch_result, "publication", doi, url)
            record = store_source_result(session, snapshot_id, result, preserve_success=force)
            counts[record.fetch_status] += 1
            completed += 1
            if progress:
                progress("semantic_scholar", completed, total, counts)
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
            record = store_source_result(session, snapshot_id, result, preserve_success=force)
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
        record = store_source_result(session, snapshot_id, result, preserve_success=force)
        counts[record.fetch_status] += 1
        completed += 1
        if progress:
            progress("openalex_author_publications", completed, total, counts)
    return counts


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
