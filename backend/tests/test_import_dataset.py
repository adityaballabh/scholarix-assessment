from pathlib import Path
from zipfile import ZipFile

import pytest
from merge_review.import_dataset import AUTHORS_ARCHIVE, normalize_doi, read_dataset
from merge_review.import_dataset import import_dataset as import_dataset_archive
from merge_review.models import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_read_dataset() -> None:
    authors = read_dataset(AUTHORS_ARCHIVE)

    assert len(authors) == 50
    assert len({author.profile["id"] for author in authors}) == 50
    assert sum(len(author.publications) for author in authors) == 5_371
    assert sum(len(author.broad_impact) for author in authors) == 343


def test_normalize_doi() -> None:
    assert normalize_doi("https://doi.org/https://doi.org/10.123/X") == "10.123/x"
    assert normalize_doi(None) is None


def test_read_dataset_rejects_empty_archive(tmp_path: Path) -> None:
    archive_path = tmp_path / "authors.zip"
    with ZipFile(archive_path, "w"):
        pass

    with pytest.raises(ValueError, match="Archive contains no author records"):
        read_dataset(archive_path)


def test_import_dataset() -> None:
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory.begin() as session:
        first = import_dataset_archive(session, AUTHORS_ARCHIVE)

    with session_factory.begin() as session:
        second = import_dataset_archive(session, AUTHORS_ARCHIVE)

    assert first.imported is True
    assert first.authors == 50
    assert first.publications == 5_371
    assert first.broad_impact_records == 343
    assert second.imported is False
    assert second.snapshot_id == first.snapshot_id
