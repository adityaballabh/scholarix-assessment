from uuid import uuid4

from merge_review.models import Base, DatasetSnapshot, ReviewSettings
from merge_review.rebuild_queue import rebuild_queue
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_queue_rebuild_records_completion(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'queue.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    snapshot_id = uuid4()

    with factory.begin() as session:
        session.add(DatasetSnapshot(id=snapshot_id, dataset_sha256="d" * 64))

    with factory.begin() as session:
        case_count = rebuild_queue(session, snapshot_id)

    with factory() as session:
        settings = session.get(ReviewSettings, snapshot_id)

    assert case_count == 0
    assert settings.queue_updated_at is not None
