import time
from collections import Counter
from dataclasses import replace
from uuid import UUID

from requests import Session
from sqlalchemy.orm import Session as DatabaseSession

from merge_review.sources.common import (
    FetchStatus,
    SourceResult,
    ProgressCallback,
    batches,
    completed_counts,
    completed_keys,
    expand_result,
    request_json,
    store_source_result,
)

BATCH_SIZE = 500
RATE_LIMIT_ATTEMPTS = 4
# Linear, so the waits are 0s, 5s, 10s, 15s before giving up on a batch.
RATE_LIMIT_BACKOFF_SECONDS = 5


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
    prior = (
        Counter()
        if force
        else completed_counts(session, snapshot_id, "semantic_scholar", "publication")
    )
    results = fetch_semantic_scholar_records(http_session, pending, progress)
    return prior + store_semantic_scholar_records(session, snapshot_id, results, force=force)


def store_semantic_scholar_records(
    session: DatabaseSession,
    snapshot_id: UUID,
    results: list[SourceResult],
    force: bool = False,
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for result in results:
        record = store_source_result(session, snapshot_id, result, preserve_success=force)
        counts[record.fetch_status] += 1
    return counts


def fetch_semantic_scholar_records(
    http_session: Session,
    dois: list[str],
    progress: ProgressCallback | None = None,
) -> list[SourceResult]:
    """Network only, so this can run off the main thread while other sources sync.

    Persisting is left to store_semantic_scholar_records, which keeps every write
    on one session inside the caller's transaction.
    """
    results: list[SourceResult] = []
    counts: Counter[str] = Counter()
    total = len(dois)
    for batch in batches(dois, BATCH_SIZE):
        for attempt in range(RATE_LIMIT_ATTEMPTS):
            time.sleep(RATE_LIMIT_BACKOFF_SECONDS * attempt)
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
            results.append(result)
            counts[result.fetch_status] += 1

        # A batch is the unit of work: 500 records land at once, so reporting
        # per DOI would only ever show the first of each burst.
        if progress:
            progress("semantic_scholar", len(results), total, counts)
    return results
