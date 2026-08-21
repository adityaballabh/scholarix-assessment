from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID

from requests import Session
from requests.exceptions import RequestException, Timeout
from requests_cache import CachedSession
from requests_ratelimiter import LimiterAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session as DatabaseSession

from merge_review.config import get_settings
from merge_review.database import SessionFactory, create_schema
from merge_review.models import Author, DatasetSnapshot, SourceRecord

PROJECT_DIR = Path(__file__).resolve().parents[3]
CACHE_PATH = PROJECT_DIR / "cache" / "http_cache"
REQUEST_TIMEOUT_SECONDS = 30


class FetchStatus(StrEnum):
    SUCCESS = "success"
    PENDING = "pending"
    NEVER_ATTEMPTED = "never_attempted"
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
    payload: dict[str, Any] | None


def create_http_session() -> CachedSession:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    session = CachedSession(
        CACHE_PATH,
        backend="sqlite",
        allowable_codes=(200, 404),
        allowable_methods=("GET",),
    )
    session.mount("https://api.openalex.org", LimiterAdapter(per_second=10))
    return session


def response_time(response: object) -> datetime:
    created_at = getattr(response, "created_at", None)
    return created_at if isinstance(created_at, datetime) else datetime.now(UTC)


def failed_result(
    author_id: str,
    status: FetchStatus,
    error: str,
    fetched_at: datetime | None = None,
    http_status: int | None = None,
    from_cache: bool = False,
) -> SourceResult:
    return SourceResult(
        source="openalex",
        entity_type="author",
        entity_key=author_id,
        source_record_id=None,
        url=f"https://openalex.org/{author_id}",
        fetch_status=status,
        http_status=http_status,
        fetched_at=fetched_at or datetime.now(UTC),
        from_cache=from_cache,
        error=error,
        payload=None,
    )


def fetch_openalex_author(
    session: Session,
    author_id: str,
    mailto: str | None = None,
) -> SourceResult:
    params = {"mailto": mailto} if mailto else None

    try:
        response = session.get(
            f"https://api.openalex.org/authors/{author_id}",
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except Timeout:
        return failed_result(author_id, FetchStatus.TIMEOUT, "Request timed out")
    except RequestException as error:
        return failed_result(author_id, FetchStatus.ERROR, str(error))

    fetched_at = response_time(response)
    from_cache = bool(getattr(response, "from_cache", False))
    if response.status_code == 404:
        return failed_result(
            author_id,
            FetchStatus.NOT_FOUND,
            "HTTP 404",
            fetched_at,
            response.status_code,
            from_cache,
        )
    if response.status_code == 429:
        return failed_result(
            author_id,
            FetchStatus.RATE_LIMITED,
            "HTTP 429",
            fetched_at,
            response.status_code,
            from_cache,
        )
    if not response.ok:
        return failed_result(
            author_id,
            FetchStatus.ERROR,
            f"HTTP {response.status_code}",
            fetched_at,
            response.status_code,
            from_cache,
        )

    try:
        payload = response.json()
    except ValueError:
        return failed_result(
            author_id,
            FetchStatus.ERROR,
            "Response was not valid JSON",
            fetched_at,
            response.status_code,
            from_cache,
        )

    if not isinstance(payload, dict) or not payload:
        return failed_result(
            author_id,
            FetchStatus.EMPTY,
            "Response contained no author record",
            fetched_at,
            response.status_code,
            from_cache,
        )

    source_record_id = payload.get("id")
    return SourceResult(
        source="openalex",
        entity_type="author",
        entity_key=author_id,
        source_record_id=source_record_id if isinstance(source_record_id, str) else author_id,
        url=f"https://openalex.org/{author_id}",
        fetch_status=FetchStatus.SUCCESS,
        http_status=response.status_code,
        fetched_at=fetched_at,
        from_cache=from_cache,
        error=None,
        payload=payload,
    )


def store_source_result(
    session: DatabaseSession,
    snapshot_id: UUID,
    result: SourceResult,
) -> SourceRecord:
    record = session.scalar(
        select(SourceRecord).where(
            SourceRecord.dataset_snapshot_id == snapshot_id,
            SourceRecord.source == result.source,
            SourceRecord.entity_type == result.entity_type,
            SourceRecord.entity_key == result.entity_key,
        )
    )
    if record is None:
        record = SourceRecord(
            dataset_snapshot_id=snapshot_id,
            source=result.source,
            entity_type=result.entity_type,
            entity_key=result.entity_key,
            source_record_id=result.source_record_id,
            url=result.url,
            fetch_status=result.fetch_status,
            http_status=result.http_status,
            fetched_at=result.fetched_at,
            from_cache=result.from_cache,
            error=result.error,
            payload=result.payload,
        )
        session.add(record)
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


def sync_openalex_authors(
    session: DatabaseSession,
    http_session: Session,
    snapshot_id: UUID,
    mailto: str | None = None,
) -> Counter[str]:
    author_ids = session.scalars(
        select(Author.source_id)
        .where(Author.dataset_snapshot_id == snapshot_id)
        .order_by(Author.source_id)
    )
    successful_ids = set(
        session.scalars(
            select(SourceRecord.entity_key).where(
                SourceRecord.dataset_snapshot_id == snapshot_id,
                SourceRecord.source == "openalex",
                SourceRecord.entity_type == "author",
                SourceRecord.fetch_status == FetchStatus.SUCCESS,
            )
        )
    )
    counts: Counter[str] = Counter()

    for author_id in author_ids:
        if author_id in successful_ids:
            counts[FetchStatus.SUCCESS] += 1
            continue

        result = fetch_openalex_author(http_session, author_id, mailto)
        store_source_result(session, snapshot_id, result)
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
