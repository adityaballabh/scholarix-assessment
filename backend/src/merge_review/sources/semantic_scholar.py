import time
from collections import Counter
from dataclasses import replace
from uuid import UUID

from requests import Session
from sqlalchemy.orm import Session as DatabaseSession

from merge_review.sources.common import (
    FetchStatus,
    ProgressCallback,
    batches,
    completed_counts,
    completed_keys,
    expand_result,
    request_json,
    store_source_result,
)


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
