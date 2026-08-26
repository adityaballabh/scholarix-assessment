from collections import Counter
from contextlib import nullcontext
from unittest.mock import Mock
from uuid import uuid4

import merge_review.fetch as fetch_module
from merge_review.models import Author, Base, DatasetSnapshot, FetchRun
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_failed_fetch_rolls_back_source_transaction(tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'fetch.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    snapshot_id = uuid4()
    author_id = uuid4()
    fetch_id = uuid4()

    with factory.begin() as session:
        session.add(DatasetSnapshot(id=snapshot_id, dataset_sha256="a" * 64))
        session.flush()
        session.add(
            Author(
                id=author_id,
                dataset_snapshot_id=snapshot_id,
                source_id="dummy",
                slug="Dummy_Author",
                name="Dummy Author",
                profile={},
            )
        )
        session.add(
            FetchRun(
                id=fetch_id,
                dataset_snapshot_id=snapshot_id,
                status="queued",
                source_progress={},
            )
        )

    def fail_after_change(session, *_args, **_kwargs):
        author = session.get(Author, author_id)
        author.name = "Changed Author"
        session.flush()
        raise RuntimeError("Source failed")

    monkeypatch.setattr(fetch_module, "SessionFactory", factory)
    monkeypatch.setattr(
        fetch_module,
        "http_session_context",
        lambda _use_cache: nullcontext(Mock()),
    )
    monkeypatch.setattr(fetch_module, "sync_openalex_authors", fail_after_change)

    fetch_module.run_fetch(fetch_id, snapshot_id)

    with factory() as session:
        fetch = session.get(FetchRun, fetch_id)
        author = session.get(Author, author_id)

    assert fetch.status == "failed"
    assert fetch.error == "Source failed"
    assert fetch.started_at is not None
    assert fetch.finished_at is not None
    assert author.name == "Dummy Author"


def test_fetch_completes_and_records_progress(tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'fetch-success.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    snapshot_id = uuid4()
    fetch_id = uuid4()

    with factory.begin() as session:
        session.add(DatasetSnapshot(id=snapshot_id, dataset_sha256="b" * 64))
        session.flush()
        session.add(
            Author(
                dataset_snapshot_id=snapshot_id,
                source_id="dummy",
                slug="Dummy_Author",
                name="Dummy Author",
                profile={},
            )
        )
        session.add(
            FetchRun(
                id=fetch_id,
                dataset_snapshot_id=snapshot_id,
                status="queued",
                source_progress={},
            )
        )

    def complete_stage(*_args, **kwargs):
        progress = kwargs["progress"]
        progress("openalex_authors", 1, 1, Counter({"success": 1}))
        return Counter({"success": 1})

    monkeypatch.setattr(fetch_module, "SessionFactory", factory)
    monkeypatch.setattr(
        fetch_module,
        "http_session_context",
        lambda _use_cache: nullcontext(Mock()),
    )
    monkeypatch.setattr(fetch_module, "sync_openalex_authors", complete_stage)
    monkeypatch.setattr(
        fetch_module,
        "sync_openalex_author_publications",
        lambda *_args, **_kwargs: Counter(),
    )
    monkeypatch.setattr(fetch_module, "rebuild_queue", lambda *_args, **_kwargs: 0)

    fetch_module.run_fetch(fetch_id, snapshot_id)

    with factory() as session:
        fetch = session.get(FetchRun, fetch_id)

    assert fetch.status == "complete"
    assert fetch.error is None
    assert {
        key: value
        for key, value in fetch.source_progress["openalex_authors"].items()
        if key != "completed_at"
    } == {
        "completed": 1,
        "total": 1,
        "by_status": {"success": 1},
    }
    assert fetch.source_progress["openalex_authors"]["completed_at"] is not None
    assert fetch.source_progress["case_generation"]["completed"] == 1


def test_interrupted_fetches_fail_on_startup(tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'fetch-recovery.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    snapshot_id = uuid4()
    fetch_ids = [uuid4(), uuid4(), uuid4()]

    with factory.begin() as session:
        session.add(DatasetSnapshot(id=snapshot_id, dataset_sha256="c" * 64))
        session.flush()
        session.add_all(
            [
                FetchRun(
                    id=fetch_ids[0],
                    dataset_snapshot_id=snapshot_id,
                    status="queued",
                    source_progress={},
                ),
                FetchRun(
                    id=fetch_ids[1],
                    dataset_snapshot_id=snapshot_id,
                    status="running",
                    source_progress={},
                ),
                FetchRun(
                    id=fetch_ids[2],
                    dataset_snapshot_id=snapshot_id,
                    status="complete",
                    source_progress={},
                ),
            ]
        )

    monkeypatch.setattr(fetch_module, "SessionFactory", factory)
    fetch_module.fail_interrupted_fetches()

    with factory() as session:
        fetches = [session.get(FetchRun, fetch_id) for fetch_id in fetch_ids]

    assert [fetch.status for fetch in fetches] == ["failed", "failed", "complete"]
    assert fetches[0].error == "Fetch interrupted by server restart"
    assert fetches[1].finished_at is not None
