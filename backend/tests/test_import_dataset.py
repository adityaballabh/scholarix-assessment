import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from merge_review.import_dataset import AUTHORS_ARCHIVE, normalize_doi, read_dataset
from merge_review.import_dataset import import_dataset as import_dataset_archive
from merge_review.models import Author, Base, PublicationRecord
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


def write_archive(
    path: Path,
    *,
    profile: object,
    publications: object,
    broad_impact: object | None = None,
) -> None:
    with ZipFile(path, "w") as archive:
        archive.writestr("authors/Dummy_Author/profile.json", json.dumps(profile))
        archive.writestr("authors/Dummy_Author/publications.json", json.dumps(publications))
        if broad_impact is not None:
            archive.writestr(
                "authors/Dummy_Author/broad_impact.json",
                json.dumps(broad_impact),
            )


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


@pytest.mark.parametrize(
    ("profile", "publications", "message"),
    [
        ({"id": "   ", "name": "Dummy"}, [], "no author ID"),
        ({"id": "A1", "name": "   "}, [], "no author name"),
        ({"id": "A1", "name": "Dummy"}, [{"title": "   "}], "without a title"),
        (
            {"id": "A1", "name": "Dummy", "orcid": {"orcid_id": 123}},
            [],
            "invalid ORCID identifier",
        ),
    ],
)
def test_read_dataset_rejects_invalid_operational_fields(
    tmp_path: Path,
    profile: object,
    publications: object,
    message: str,
) -> None:
    archive_path = tmp_path / "authors.zip"
    write_archive(archive_path, profile=profile, publications=publications)

    with pytest.raises(ValueError, match=message):
        read_dataset(archive_path)


def test_read_dataset_preserves_duplicate_occurrences_and_payloads(tmp_path: Path) -> None:
    archive_path = tmp_path / "authors.zip"
    publications = [
        {"title": "Same work", "doi": "10.123/example", "source": "openalex"},
        {"title": "Same work", "doi": "10.123/example", "source": "crossref"},
    ]
    write_archive(
        archive_path,
        profile={"id": "A1", "name": "Dummy Author"},
        publications=publications,
    )

    authors = read_dataset(archive_path)

    assert authors[0].publications == publications


def test_import_normalizes_operational_text_and_preserves_raw_payload(tmp_path: Path) -> None:
    archive_path = tmp_path / "authors.zip"
    write_archive(
        archive_path,
        profile={
            "id": " A1 ",
            "name": " Dummy Author ",
            "affiliation": " Dummy University ",
            "orcid": {"orcid_id": " 0000-0000-0000-0000 "},
        },
        publications=[{"title": " Dummy Publication "}],
    )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    with factory.begin() as session:
        import_dataset_archive(session, archive_path)
    with factory() as session:
        author = session.scalar(select(Author))
        publication = session.scalar(select(PublicationRecord))

    assert author.source_id == "A1"
    assert author.name == "Dummy Author"
    assert author.affiliation == "Dummy University"
    assert author.orcid_id == "0000-0000-0000-0000"
    assert author.profile["name"] == " Dummy Author "
    assert publication.title == "Dummy Publication"
    assert publication.payload["title"] == " Dummy Publication "


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
