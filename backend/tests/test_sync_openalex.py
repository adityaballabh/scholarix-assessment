from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest
from merge_review.models import Author, Base, DatasetSnapshot, SourceRecord
from merge_review.sync_openalex import (
    FetchStatus,
    fetch_openalex_author,
    sync_openalex_authors,
)
from requests.exceptions import Timeout
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

DUMMY_AUTHOR_ID = "dummy"
DUMMY_AUTHOR_NAME = "Dummy Author"


def make_response(status_code: int, payload: object | None = None) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 400
    response.created_at = datetime(2026, 8, 23, tzinfo=UTC)
    response.from_cache = False
    if payload is None:
        response.json.side_effect = ValueError
    else:
        response.json.return_value = payload
    return response


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
    http_session.get.return_value = response

    result = fetch_openalex_author(http_session, DUMMY_AUTHOR_ID)

    assert result.fetch_status == expected
    assert result.entity_key == DUMMY_AUTHOR_ID


def test_fetch_openalex_author_timeout() -> None:
    http_session = Mock()
    http_session.get.side_effect = Timeout

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
    http_session.get.return_value = make_response(429)
    with session_factory.begin() as session:
        first_counts = sync_openalex_authors(session, http_session, snapshot_id)

    http_session.get.return_value = make_response(
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

    http_session.get.return_value = make_response(429)
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
    assert http_session.get.call_count == 2
