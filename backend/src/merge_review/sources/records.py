from collections import Counter
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from merge_review.models import SourceRecord
from merge_review.sources.common import FetchStatus, SourceResult

TRANSIENT_FAILURE_STATUSES = {
    FetchStatus.RATE_LIMITED,
    FetchStatus.TIMEOUT,
    FetchStatus.ERROR,
}


def store_source_result(
    session: Session,
    snapshot_id: UUID,
    result: SourceResult,
    preserve_success: bool = False,
) -> SourceRecord:
    records = source_record_map(session, snapshot_id)
    key = result.source, result.entity_type, result.entity_key
    record = records.get(key)
    if record is None:
        record = SourceRecord(
            dataset_snapshot_id=snapshot_id,
            source=result.source,
            entity_type=result.entity_type,
            entity_key=result.entity_key,
        )
        session.add(record)
        records[key] = record

    # A forced refresh failure must not erase successful evidence already in hand
    if (
        preserve_success
        and record.fetch_status == FetchStatus.SUCCESS
        and result.fetch_status in TRANSIENT_FAILURE_STATUSES
    ):
        return record

    record.source_record_id = result.source_record_id
    record.url = result.url
    record.fetch_status = result.fetch_status
    record.http_status = result.http_status
    record.fetched_at = result.fetched_at
    record.from_cache = result.from_cache
    record.error = result.error
    record.payload = result.payload
    return record


def source_record_map(
    session: Session,
    snapshot_id: UUID,
) -> dict[tuple[str, str, str], SourceRecord]:
    cache_key = f"source_records:{snapshot_id}"
    records = session.info.get(cache_key)
    if records is None:
        records = {
            (record.source, record.entity_type, record.entity_key): record
            for record in session.scalars(
                select(SourceRecord).where(SourceRecord.dataset_snapshot_id == snapshot_id)
            )
        }
        session.info[cache_key] = records
    return records


def completed_keys(
    session: Session,
    snapshot_id: UUID,
    source: str,
    entity_type: str,
) -> set[str]:
    return set(
        session.scalars(
            select(SourceRecord.entity_key).where(
                SourceRecord.dataset_snapshot_id == snapshot_id,
                SourceRecord.source == source,
                SourceRecord.entity_type == entity_type,
                SourceRecord.fetch_status.in_(
                    [FetchStatus.SUCCESS, FetchStatus.NOT_FOUND, FetchStatus.EMPTY]
                ),
            )
        )
    )


def completed_counts(
    session: Session,
    snapshot_id: UUID,
    source: str,
    entity_type: str,
) -> Counter[str]:
    rows = session.execute(
        select(SourceRecord.fetch_status, func.count())
        .where(
            SourceRecord.dataset_snapshot_id == snapshot_id,
            SourceRecord.source == source,
            SourceRecord.entity_type == entity_type,
            SourceRecord.fetch_status.in_(
                [FetchStatus.SUCCESS, FetchStatus.NOT_FOUND, FetchStatus.EMPTY]
            ),
        )
        .group_by(SourceRecord.fetch_status)
    )
    return Counter({status: count for status, count in rows})
