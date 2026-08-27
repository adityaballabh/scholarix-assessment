from collections import Counter
from dataclasses import replace
from uuid import UUID

from requests import Session
from sqlalchemy import select
from sqlalchemy.orm import Session as DatabaseSession

from merge_review.models import Author
from merge_review.sources.common import (
    FetchStatus,
    ProgressCallback,
    request_json,
)
from merge_review.sources.records import completed_counts, completed_keys, store_source_result


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
