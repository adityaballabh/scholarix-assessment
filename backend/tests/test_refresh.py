from collections import Counter
from contextlib import ExitStack
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from merge_review.models import Author, Base, DatasetSnapshot, PublicationRecord
from merge_review.sources.common import FetchStatus
from merge_review.sources.refresh import (
    author_dois,
    refresh_all_author_sources,
    refresh_author_source,
    refresh_source,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DUMMY_ORCID = "0000-0000-0000-0000"
DUMMY_DOIS = ("10.123/first", "10.123/second")

SYNC_FUNCTIONS = (
    "sync_openalex_authors",
    "sync_openalex_author_publications",
    "sync_openalex_publication_records",
    "sync_semantic_scholar_records",
    "sync_orcid_records",
)


@pytest.fixture
def author_session():
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    snapshot_id = uuid4()
    author_id = uuid4()

    with factory.begin() as session:
        session.add(DatasetSnapshot(id=snapshot_id, dataset_sha256="a" * 64))
        session.flush()
        session.add(
            Author(
                id=author_id,
                dataset_snapshot_id=snapshot_id,
                source_id="A123",
                slug="Dummy_Author",
                name="Dummy Author",
                orcid_id=DUMMY_ORCID,
                profile={},
            )
        )
        session.add_all(
            PublicationRecord(
                author_id=author_id,
                position=position,
                normalized_doi=doi,
                title=f"Dummy Publication {position + 1}",
                source="openalex",
                payload={},
            )
            for position, doi in enumerate(DUMMY_DOIS)
        )

    with factory() as session:
        yield session, session.get(Author, author_id)


def run_refresh(call) -> tuple[Counter[str], set[str], dict]:
    with ExitStack() as stack:
        mocks = {
            name: stack.enter_context(
                patch(
                    f"merge_review.sources.refresh.{name}",
                    return_value=Counter({FetchStatus.SUCCESS: 1}),
                )
            )
            for name in SYNC_FUNCTIONS
        }
        counts = call()
    called = {name for name, mock in mocks.items() if mock.call_count}
    return counts, called, mocks


def test_author_dois_are_deduplicated_and_ordered(author_session) -> None:
    session, author = author_session

    assert author_dois(session, author.id) == list(DUMMY_DOIS)


def test_refreshing_openalex_covers_the_author_and_their_publications(author_session) -> None:
    session, author = author_session

    counts, called, mocks = run_refresh(
        lambda: refresh_author_source(session, Mock(), author, "openalex")
    )

    assert called == {
        "sync_openalex_authors",
        "sync_openalex_author_publications",
        "sync_openalex_publication_records",
    }
    assert set(counts) == {
        "openalex_author:success",
        "openalex_author_publications:success",
        "openalex_publications:success",
    }
    assert mocks["sync_openalex_publication_records"].call_args.args[3] == list(DUMMY_DOIS)


def test_refreshing_semantic_scholar_only_refetches_publications(author_session) -> None:
    session, author = author_session

    counts, called, mocks = run_refresh(
        lambda: refresh_author_source(session, Mock(), author, "semantic_scholar")
    )

    assert called == {"sync_semantic_scholar_records"}
    assert set(counts) == {"semantic_scholar:success"}
    assert mocks["sync_semantic_scholar_records"].call_args.args[3] == list(DUMMY_DOIS)


def test_refreshing_orcid_does_not_touch_publication_sources(author_session) -> None:
    session, author = author_session

    counts, called, _ = run_refresh(lambda: refresh_author_source(session, Mock(), author, "orcid"))

    assert called == {"sync_orcid_records"}
    assert set(counts) == {"orcid:success"}


def test_fetching_every_source_skips_orcid_when_the_author_has_none(author_session) -> None:
    session, author = author_session
    author.orcid_id = None

    counts, called, _ = run_refresh(lambda: refresh_author_source(session, Mock(), author, "orcid"))

    assert called == set()
    assert counts == Counter()


def test_refreshing_a_whole_author_covers_every_source(author_session) -> None:
    session, author = author_session

    _, called, _ = run_refresh(lambda: refresh_all_author_sources(session, Mock(), author))

    assert called == set(SYNC_FUNCTIONS)


def test_refreshing_a_source_spans_the_whole_snapshot(author_session) -> None:
    session, author = author_session

    _, openalex_called, mocks = run_refresh(
        lambda: refresh_source(session, Mock(), author.dataset_snapshot_id, "openalex")
    )
    _, orcid_called, _ = run_refresh(
        lambda: refresh_source(session, Mock(), author.dataset_snapshot_id, "orcid")
    )

    assert openalex_called == {
        "sync_openalex_authors",
        "sync_openalex_author_publications",
        "sync_openalex_publication_records",
    }
    assert mocks["sync_openalex_publication_records"].call_args.args[3] == list(DUMMY_DOIS)
    assert orcid_called == {"sync_orcid_records"}
