from datetime import UTC, datetime
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

from merge_review.models import Base, DatasetSnapshot, SourceRecord
from merge_review.source_records import FetchStatus
from merge_review.sync_sources import (
    absent_keys,
    sync_openalex_publication_records,
    sync_semantic_scholar_records,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

DUMMY_SNAPSHOT_HASH = "a" * 64
DUMMY_FOUND_DOI = "10.123/found"
DUMMY_MISSING_DOI = "10.123/missing"
DUMMY_SEMANTIC_SCHOLAR_PAPER_ID = "paperID"
DUMMY_OPENALEX_WORK_ID = "W123"
DUMMY_FETCHED_AT = datetime(2026, 8, 21, tzinfo=UTC)


def session_factory():
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def make_response(status_code: int, payload: object | None = None) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 400
    response.created_at = DUMMY_FETCHED_AT
    response.from_cache = False
    response.headers = {}
    response.json.return_value = payload
    return response


def add_snapshot(factory) -> UUID:
    snapshot_id = uuid4()
    with factory.begin() as session:
        session.add(DatasetSnapshot(id=snapshot_id, dataset_sha256=DUMMY_SNAPSHOT_HASH))
    return snapshot_id


def test_absent_keys_excludes_transient_failures() -> None:
    factory = session_factory()
    snapshot_id = add_snapshot(factory)
    now = datetime.now(UTC)

    with factory.begin() as session:
        session.add_all(
            [
                SourceRecord(
                    dataset_snapshot_id=snapshot_id,
                    source="crossref",
                    entity_type="publication",
                    entity_key="missing",
                    fetch_status=FetchStatus.NOT_FOUND,
                    fetched_at=now,
                    from_cache=False,
                ),
                SourceRecord(
                    dataset_snapshot_id=snapshot_id,
                    source="crossref",
                    entity_type="publication",
                    entity_key="retry",
                    fetch_status=FetchStatus.RATE_LIMITED,
                    fetched_at=now,
                    from_cache=False,
                ),
            ]
        )

    with factory() as session:
        keys = absent_keys(session, snapshot_id, "crossref")

    assert keys == {"missing"}


def test_semantic_scholar_batch_persists_found_and_missing_records() -> None:
    factory = session_factory()
    snapshot_id = add_snapshot(factory)
    http_session = Mock()
    http_session.request.side_effect = [
        make_response(429),
        make_response(
            200,
            [
                {
                    "paperId": DUMMY_SEMANTIC_SCHOLAR_PAPER_ID,
                    "externalIds": {"DOI": DUMMY_FOUND_DOI},
                    "authors": [],
                },
                None,
            ],
        ),
    ]

    with patch("merge_review.sync_sources.time.sleep") as sleep:
        with factory.begin() as session:
            counts = sync_semantic_scholar_records(
                session,
                http_session,
                snapshot_id,
                [DUMMY_FOUND_DOI, DUMMY_MISSING_DOI],
            )

    with factory() as session:
        records = {
            record.entity_key: record for record in session.scalars(select(SourceRecord)).all()
        }

    assert counts == {FetchStatus.SUCCESS: 1, FetchStatus.NOT_FOUND: 1}
    assert records[DUMMY_FOUND_DOI].source_record_id == DUMMY_SEMANTIC_SCHOLAR_PAPER_ID
    assert records[DUMMY_MISSING_DOI].fetch_status == FetchStatus.NOT_FOUND
    assert sleep.call_count == 2


def test_semantic_scholar_batch_rejects_malformed_paper() -> None:
    factory = session_factory()
    snapshot_id = add_snapshot(factory)
    http_session = Mock()
    http_session.request.return_value = make_response(200, [{}])

    with factory.begin() as session:
        counts = sync_semantic_scholar_records(
            session,
            http_session,
            snapshot_id,
            [DUMMY_FOUND_DOI],
        )

    with factory() as session:
        record = session.scalar(select(SourceRecord))

    assert counts == {FetchStatus.ERROR: 1}
    assert record.fetch_status == FetchStatus.ERROR
    assert record.error == "Semantic Scholar returned a malformed paper record"


def test_openalex_batch_persists_found_and_missing_records() -> None:
    factory = session_factory()
    snapshot_id = add_snapshot(factory)
    http_session = Mock()
    http_session.request.return_value = make_response(
        200,
        {
            "results": [
                {
                    "id": f"https://openalex.org/{DUMMY_OPENALEX_WORK_ID}",
                    "doi": f"https://doi.org/{DUMMY_FOUND_DOI}",
                }
            ],
            "meta": {"next_cursor": None},
        },
    )

    with factory.begin() as session:
        counts = sync_openalex_publication_records(
            session,
            http_session,
            snapshot_id,
            [DUMMY_FOUND_DOI, DUMMY_MISSING_DOI],
            None,
        )

    assert counts == {FetchStatus.SUCCESS: 1, FetchStatus.NOT_FOUND: 1}
