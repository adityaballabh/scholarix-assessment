from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from itertools import islice
from pathlib import Path
from typing import Any
from uuid import UUID

from requests import Session
from requests.exceptions import RequestException, Timeout
from requests_cache import CachedSession
from requests_ratelimiter import LimiterAdapter
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DatabaseSession

from merge_review.models import SourceRecord

PROJECT_DIR = Path(__file__).resolve().parents[4]
CACHE_PATH = PROJECT_DIR / "cache" / "http_cache"
REQUEST_TIMEOUT_SECONDS = 30
ProgressCallback = Callable[[str, int, int, Counter[str]], None]


class FetchStatus(StrEnum):
    SUCCESS = "success"
    PENDING = "pending"
    NOT_APPLICABLE = "not_applicable"
    EMPTY = "empty"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass(frozen=True)
class SourceResult:
    source: str
    entity_type: str
    entity_key: str
    source_record_id: str | None
    url: str | None
    fetch_status: FetchStatus
    http_status: int | None
    fetched_at: datetime
    from_cache: bool
    error: str | None
    payload: Any | None


def batches(values: Iterable[str], size: int) -> Iterable[list[str]]:
    iterator = iter(values)
    while batch := list(islice(iterator, size)):
        yield batch


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


def create_http_session() -> CachedSession:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    session = CachedSession(
        CACHE_PATH,
        backend="sqlite",
        allowable_codes=(200, 302, 404),
        allowable_methods=("GET", "POST"),
    )
    limits = {
        "https://api.openalex.org": 10,
        "https://pub.orcid.org": 10,
        "https://api.semanticscholar.org": 1,
    }
    for host, rate in limits.items():
        session.mount(host, LimiterAdapter(per_second=rate))
    return session


@contextmanager
def uncached_http_session() -> Iterator[CachedSession]:
    session = create_http_session()
    try:
        with session.cache_disabled():
            yield session
    finally:
        session.close()


def request_json(
    session: Session,
    source: str,
    entity_type: str,
    entity_key: str,
    request_url: str,
    record_url: str | None = None,
    method: str = "GET",
    **kwargs: Any,
) -> SourceResult:
    try:
        response = session.request(
            method,
            request_url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            **kwargs,
        )
    except Timeout:
        return failed_result(
            source,
            entity_type,
            entity_key,
            record_url or request_url,
            FetchStatus.TIMEOUT,
            "Request timed out",
        )
    except RequestException as error:
        return failed_result(
            source,
            entity_type,
            entity_key,
            record_url or request_url,
            FetchStatus.ERROR,
            str(error),
        )

    fetched_at = getattr(response, "created_at", None)
    if not isinstance(fetched_at, datetime):
        fetched_at = datetime.now(UTC)
    from_cache = bool(getattr(response, "from_cache", False))
    common = {
        "source": source,
        "entity_type": entity_type,
        "entity_key": entity_key,
        "url": record_url or request_url,
        "fetched_at": fetched_at,
        "http_status": response.status_code,
        "from_cache": from_cache,
    }

    if response.status_code == 404:
        return failed_result(**common, status=FetchStatus.NOT_FOUND, error="HTTP 404")
    if response.status_code == 429:
        return failed_result(**common, status=FetchStatus.RATE_LIMITED, error="HTTP 429")
    if not response.ok:
        return failed_result(
            **common,
            status=FetchStatus.ERROR,
            error=f"HTTP {response.status_code}",
        )

    try:
        payload = response.json()
    except ValueError:
        return failed_result(
            **common,
            status=FetchStatus.ERROR,
            error="Response was not valid JSON",
        )

    if payload is None or payload == {} or payload == []:
        return failed_result(
            **common,
            status=FetchStatus.EMPTY,
            error="Response contained no record",
        )

    return SourceResult(
        **common,
        source_record_id=None,
        fetch_status=FetchStatus.SUCCESS,
        error=None,
        payload=payload,
    )


def failed_result(
    source: str,
    entity_type: str,
    entity_key: str,
    url: str,
    status: FetchStatus,
    error: str,
    fetched_at: datetime | None = None,
    http_status: int | None = None,
    from_cache: bool = False,
) -> SourceResult:
    return SourceResult(
        source=source,
        entity_type=entity_type,
        entity_key=entity_key,
        source_record_id=None,
        url=url,
        fetch_status=status,
        http_status=http_status,
        fetched_at=fetched_at or datetime.now(UTC),
        from_cache=from_cache,
        error=error,
        payload=None,
    )


def store_source_result(
    session: DatabaseSession,
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

    if (
        preserve_success
        and record.fetch_status == FetchStatus.SUCCESS
        and result.fetch_status != FetchStatus.SUCCESS
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
    session: DatabaseSession,
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
    session: DatabaseSession,
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
    session: DatabaseSession,
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
