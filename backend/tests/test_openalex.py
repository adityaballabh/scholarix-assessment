from unittest.mock import Mock
from uuid import uuid4

import pytest
from merge_review.models import Author, Base, DatasetSnapshot, SourceRecord
from merge_review.sources.common import FetchStatus
from merge_review.sources.openalex import (
    fetch_openalex_author,
    sync_openalex_authors,
    sync_openalex_publication_records,
)
from requests.exceptions import Timeout
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from support import make_response

DUMMY_AUTHOR_ID = "dummy"
DUMMY_AUTHOR_NAME = "Dummy Author"


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (make_response(404), FetchStatus.NOT_FOUND),
        (make_response(429), FetchStatus.RATE_LIMITED),
        (make_response(500), FetchStatus.ERROR),
        (make_response(200, {}), FetchStatus.EMPTY),
    ],
)
def test_fetch_openalex_author_outcomes(response: Mock, expected: FetchStatus) -> None:
    http_session = Mock()
    http_session.request.return_value = response

    result = fetch_openalex_author(http_session, DUMMY_AUTHOR_ID)

    assert result.fetch_status == expected
    assert result.entity_key == DUMMY_AUTHOR_ID


def test_fetch_openalex_author_timeout() -> None:
    http_session = Mock()
    http_session.request.side_effect = Timeout

    result = fetch_openalex_author(http_session, DUMMY_AUTHOR_ID)

    assert result.fetch_status == FetchStatus.TIMEOUT
    assert result.http_status is None


def test_sync_openalex_authors_persists_and_updates_results() -> None:
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    snapshot_id = uuid4()

    with session_factory.begin() as session:
        session.add(DatasetSnapshot(id=snapshot_id, dataset_sha256="a" * 64))
        session.flush()
        session.add(
            Author(
                dataset_snapshot_id=snapshot_id,
                source_id=DUMMY_AUTHOR_ID,
                slug="Dummy_Author",
                name=DUMMY_AUTHOR_NAME,
                profile={},
            )
        )

    http_session = Mock()
    http_session.request.return_value = make_response(429)
    with session_factory.begin() as session:
        first_counts = sync_openalex_authors(session, http_session, snapshot_id)

    http_session.request.return_value = make_response(
        200,
        {
            "id": f"https://openalex.org/{DUMMY_AUTHOR_ID}",
            "display_name": DUMMY_AUTHOR_NAME,
        },
    )
    with session_factory.begin() as session:
        second_counts = sync_openalex_authors(session, http_session, snapshot_id)

    assert first_counts == {FetchStatus.RATE_LIMITED: 1}
    assert second_counts == {FetchStatus.SUCCESS: 1}

    http_session.request.return_value = make_response(429)
    with session_factory.begin() as session:
        third_counts = sync_openalex_authors(session, http_session, snapshot_id)

    with session_factory() as session:
        records = session.scalars(select(SourceRecord)).all()

    assert len(records) == 1
    assert records[0].fetch_status == FetchStatus.SUCCESS
    assert records[0].payload == {
        "id": f"https://openalex.org/{DUMMY_AUTHOR_ID}",
        "display_name": DUMMY_AUTHOR_NAME,
    }
    assert third_counts == {FetchStatus.SUCCESS: 1}
    assert http_session.request.call_count == 2

    http_session.request.return_value = make_response(
        200,
        {
            "id": f"https://openalex.org/{DUMMY_AUTHOR_ID}",
            "display_name": "Updated Dummy Author",
        },
    )
    with session_factory.begin() as session:
        forced_counts = sync_openalex_authors(
            session,
            http_session,
            snapshot_id,
            force=True,
        )

    with session_factory() as session:
        refreshed = session.scalar(select(SourceRecord))

    assert forced_counts == {FetchStatus.SUCCESS: 1}
    assert refreshed.payload["display_name"] == "Updated Dummy Author"
    assert http_session.request.call_count == 3

    http_session.request.return_value = make_response(429)
    with session_factory.begin() as session:
        failed_refresh_counts = sync_openalex_authors(
            session,
            http_session,
            snapshot_id,
            force=True,
        )

    with session_factory() as session:
        preserved = session.scalar(select(SourceRecord))

    assert failed_refresh_counts == {FetchStatus.SUCCESS: 1}
    assert preserved.fetch_status == FetchStatus.SUCCESS
    assert preserved.payload["display_name"] == "Updated Dummy Author"


def test_publication_batch_persists_found_and_missing_records() -> None:
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    snapshot_id = uuid4()
    found_doi = "10.123/found"
    missing_doi = "10.123/missing"
    with factory.begin() as session:
        session.add(DatasetSnapshot(id=snapshot_id, dataset_sha256="b" * 64))

    http_session = Mock()
    http_session.request.return_value = make_response(
        200,
        {
            "results": [
                {
                    "id": "https://openalex.org/W123",
                    "doi": f"https://doi.org/{found_doi}",
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
            [found_doi, missing_doi],
            None,
        )

    assert counts == {FetchStatus.SUCCESS: 1, FetchStatus.NOT_FOUND: 1}
