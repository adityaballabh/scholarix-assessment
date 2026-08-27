from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from itertools import islice
from typing import Any

from requests import Session
from requests.exceptions import RequestException, Timeout
from requests_cache import CachedSession
from requests_ratelimiter import LimiterAdapter

from merge_review.config import PROJECT_DIR

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


def http_session_context(use_cache: bool) -> AbstractContextManager[CachedSession]:
    return create_http_session() if use_cache else uncached_http_session()


@contextmanager
def uncached_http_session() -> Iterator[CachedSession]:
    session = create_http_session()
    try:
        with session.cache_disabled():
            yield session
    finally:
        session.close()


def request_json(
    http_session: Session,
    source: str,
    entity_type: str,
    entity_key: str,
    request_url: str,
    record_url: str | None = None,
    method: str = "GET",
    **kwargs: Any,
) -> SourceResult:
    try:
        response = http_session.request(
            method,
            request_url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            **kwargs,
        )
    except Timeout:
        return non_success_result(
            source,
            entity_type,
            entity_key,
            record_url or request_url,
            FetchStatus.TIMEOUT,
            "Request timed out",
        )
    except RequestException as error:
        return non_success_result(
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
        return non_success_result(**common, status=FetchStatus.NOT_FOUND, error="HTTP 404")
    if response.status_code == 429:
        return non_success_result(**common, status=FetchStatus.RATE_LIMITED, error="HTTP 429")
    if not response.ok:
        return non_success_result(
            **common,
            status=FetchStatus.ERROR,
            error=f"HTTP {response.status_code}",
        )

    try:
        payload = response.json()
    except ValueError:
        return non_success_result(
            **common,
            status=FetchStatus.ERROR,
            error="Response was not valid JSON",
        )

    if payload is None or payload == {} or payload == []:
        return non_success_result(
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


def non_success_result(
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
