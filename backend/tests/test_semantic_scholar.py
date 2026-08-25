from unittest.mock import Mock, patch
from uuid import uuid4

from conftest import make_response
from merge_review.models import Base, DatasetSnapshot, SourceRecord
from merge_review.sources.common import FetchStatus
from merge_review.sources.semantic_scholar import sync_semantic_scholar_records
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

DUMMY_FOUND_DOI = "10.123/found"
DUMMY_MISSING_DOI = "10.123/missing"
DUMMY_PAPER_ID = "paperID"


def session_factory():
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def add_snapshot(factory):
    snapshot_id = uuid4()
    with factory.begin() as session:
        session.add(DatasetSnapshot(id=snapshot_id, dataset_sha256="a" * 64))
    return snapshot_id


def test_batch_persists_found_and_missing_records() -> None:
    factory = session_factory()
    snapshot_id = add_snapshot(factory)
    http_session = Mock()
    http_session.request.side_effect = [
        make_response(429),
        make_response(
            200,
            [
                {
                    "paperId": DUMMY_PAPER_ID,
                    "externalIds": {"DOI": DUMMY_FOUND_DOI},
                    "authors": [],
                },
                None,
            ],
        ),
    ]

    with patch("merge_review.sources.semantic_scholar.time.sleep") as sleep:
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
    assert records[DUMMY_FOUND_DOI].source_record_id == DUMMY_PAPER_ID
    assert records[DUMMY_MISSING_DOI].fetch_status == FetchStatus.NOT_FOUND
    assert sleep.call_count == 2


def test_batch_rejects_malformed_paper() -> None:
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
