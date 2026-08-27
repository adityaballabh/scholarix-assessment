from datetime import UTC, datetime
from uuid import uuid4

import pytest
from merge_review.models import Base, DatasetSnapshot
from merge_review.sources.common import FetchStatus, SourceResult
from merge_review.sources.records import store_source_result
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def source_result(status: FetchStatus, payload: dict | None) -> SourceResult:
    return SourceResult(
        source="openalex",
        entity_type="publication",
        entity_key="10.123/example",
        source_record_id="W2" if payload else None,
        url="https://openalex.org/W2",
        fetch_status=status,
        http_status=200 if status == FetchStatus.SUCCESS else None,
        fetched_at=datetime.now(UTC),
        from_cache=False,
        error=None if status == FetchStatus.SUCCESS else str(status),
        payload=payload,
    )


@pytest.mark.parametrize(
    ("status", "expected_status", "expected_payload"),
    [
        (FetchStatus.RATE_LIMITED, FetchStatus.SUCCESS, {"version": 1}),
        (FetchStatus.TIMEOUT, FetchStatus.SUCCESS, {"version": 1}),
        (FetchStatus.ERROR, FetchStatus.SUCCESS, {"version": 1}),
        (FetchStatus.NOT_FOUND, FetchStatus.NOT_FOUND, None),
        (FetchStatus.EMPTY, FetchStatus.EMPTY, None),
        (FetchStatus.SUCCESS, FetchStatus.SUCCESS, {"version": 2}),
    ],
)
def test_forced_refresh_only_preserves_success_across_transient_failures(
    status: FetchStatus,
    expected_status: FetchStatus,
    expected_payload: dict | None,
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    snapshot_id = uuid4()

    with factory.begin() as session:
        session.add(DatasetSnapshot(id=snapshot_id, dataset_sha256="a" * 64))
        session.flush()
        store_source_result(
            session,
            snapshot_id,
            source_result(FetchStatus.SUCCESS, {"version": 1}),
        )
        stored = store_source_result(
            session,
            snapshot_id,
            source_result(status, {"version": 2} if status == FetchStatus.SUCCESS else None),
            preserve_success=True,
        )

    assert stored.fetch_status == expected_status
    assert stored.payload == expected_payload
