from unittest.mock import Mock
from uuid import uuid4

from merge_review.models import Author, Base, DatasetSnapshot, SourceRecord
from merge_review.sources.common import FetchStatus
from merge_review.sources.orcid import sync_orcid_records
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from support import make_response

DUMMY_ORCID = "0000-0000-0000-0000"


def author_factory():
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    snapshot_id = uuid4()
    with factory.begin() as session:
        session.add(DatasetSnapshot(id=snapshot_id, dataset_sha256="a" * 64))
        session.flush()
        session.add(
            Author(
                dataset_snapshot_id=snapshot_id,
                source_id="A123",
                slug="Dummy_Author",
                name="Dummy Author",
                orcid_id=DUMMY_ORCID,
                profile={},
            )
        )
    return factory, snapshot_id


def test_records_are_persisted_and_not_refetched() -> None:
    factory, snapshot_id = author_factory()
    http_session = Mock()
    http_session.request.return_value = make_response(
        200,
        {"orcid-identifier": {"path": DUMMY_ORCID}},
    )

    with factory.begin() as session:
        first_counts = sync_orcid_records(session, http_session, snapshot_id)
    with factory.begin() as session:
        second_counts = sync_orcid_records(session, http_session, snapshot_id)

    with factory() as session:
        record = session.scalar(select(SourceRecord))

    assert first_counts == {FetchStatus.SUCCESS: 1}
    assert second_counts == first_counts
    assert http_session.request.call_count == 1
    assert record.entity_key == DUMMY_ORCID
    assert record.source_record_id == DUMMY_ORCID
    assert record.url == f"https://orcid.org/{DUMMY_ORCID}"


def test_failed_refresh_keeps_the_stored_record() -> None:
    factory, snapshot_id = author_factory()
    http_session = Mock()
    http_session.request.return_value = make_response(
        200,
        {"orcid-identifier": {"path": DUMMY_ORCID}},
    )

    with factory.begin() as session:
        sync_orcid_records(session, http_session, snapshot_id, [DUMMY_ORCID])

    http_session.request.return_value = make_response(429)
    with factory.begin() as session:
        counts = sync_orcid_records(session, http_session, snapshot_id, [DUMMY_ORCID], force=True)

    with factory() as session:
        record = session.scalar(select(SourceRecord))

    assert counts == {FetchStatus.SUCCESS: 1}
    assert record.fetch_status == FetchStatus.SUCCESS
    assert record.payload == {"orcid-identifier": {"path": DUMMY_ORCID}}
