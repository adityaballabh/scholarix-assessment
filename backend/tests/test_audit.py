from collections import Counter
from contextlib import nullcontext
from unittest.mock import Mock
from uuid import uuid4

import merge_review.audit as audit_module
from merge_review.models import AuditRun, Author, Base, DatasetSnapshot
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_failed_audit_rolls_back_source_transaction(tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'audit.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    snapshot_id = uuid4()
    author_id = uuid4()
    audit_id = uuid4()

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
            AuditRun(
                id=audit_id,
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

    monkeypatch.setattr(audit_module, "SessionFactory", factory)
    monkeypatch.setattr(
        audit_module,
        "uncached_http_session",
        lambda: nullcontext(Mock()),
    )
    monkeypatch.setattr(audit_module, "sync_openalex_authors", fail_after_change)

    audit_module.run_full_audit(audit_id, snapshot_id)

    with factory() as session:
        audit = session.get(AuditRun, audit_id)
        author = session.get(Author, author_id)

    assert audit.status == "failed"
    assert audit.error == "Source failed"
    assert audit.started_at is not None
    assert audit.finished_at is not None
    assert author.name == "Dummy Author"


def test_audit_completes_and_records_progress(tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'audit-success.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    snapshot_id = uuid4()
    audit_id = uuid4()

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
            AuditRun(
                id=audit_id,
                dataset_snapshot_id=snapshot_id,
                status="queued",
                source_progress={},
            )
        )

    def complete_stage(*_args, **kwargs):
        progress = kwargs["progress"]
        progress("openalex_authors", 1, 1, Counter({"success": 1}))
        return Counter({"success": 1})

    monkeypatch.setattr(audit_module, "SessionFactory", factory)
    monkeypatch.setattr(
        audit_module,
        "uncached_http_session",
        lambda: nullcontext(Mock()),
    )
    monkeypatch.setattr(audit_module, "sync_openalex_authors", complete_stage)
    monkeypatch.setattr(
        audit_module,
        "sync_openalex_author_publications",
        lambda *_args, **_kwargs: Counter(),
    )
    monkeypatch.setattr(audit_module, "run_audit", lambda *_args, **_kwargs: 0)

    audit_module.run_full_audit(audit_id, snapshot_id)

    with factory() as session:
        audit = session.get(AuditRun, audit_id)

    assert audit.status == "complete"
    assert audit.error is None
    assert {
        key: value
        for key, value in audit.source_progress["openalex_authors"].items()
        if key != "completed_at"
    } == {
        "completed": 1,
        "total": 1,
        "by_status": {"success": 1},
    }
    assert audit.source_progress["openalex_authors"]["completed_at"] is not None
    assert audit.source_progress["case_generation"]["completed"] == 1


def test_interrupted_audits_fail_on_startup(tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'audit-recovery.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    snapshot_id = uuid4()
    audit_ids = [uuid4(), uuid4(), uuid4()]

    with factory.begin() as session:
        session.add(DatasetSnapshot(id=snapshot_id, dataset_sha256="c" * 64))
        session.flush()
        session.add_all(
            [
                AuditRun(
                    id=audit_ids[0],
                    dataset_snapshot_id=snapshot_id,
                    status="queued",
                    source_progress={},
                ),
                AuditRun(
                    id=audit_ids[1],
                    dataset_snapshot_id=snapshot_id,
                    status="running",
                    source_progress={},
                ),
                AuditRun(
                    id=audit_ids[2],
                    dataset_snapshot_id=snapshot_id,
                    status="complete",
                    source_progress={},
                ),
            ]
        )

    monkeypatch.setattr(audit_module, "SessionFactory", factory)
    audit_module.fail_interrupted_audits()

    with factory() as session:
        audits = [session.get(AuditRun, audit_id) for audit_id in audit_ids]

    assert [audit.status for audit in audits] == ["failed", "failed", "complete"]
    assert audits[0].error == "Audit interrupted by server restart"
    assert audits[1].finished_at is not None
