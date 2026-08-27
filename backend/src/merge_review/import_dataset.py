import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID, uuid4
from zipfile import ZipFile

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from merge_review.config import PROJECT_DIR
from merge_review.database import SessionFactory, create_schema
from merge_review.models import (
    Author,
    BroadImpactRecord,
    DatasetSnapshot,
    PublicationRecord,
)

AUTHORS_ARCHIVE = PROJECT_DIR / "dataset" / "authors.zip"
DATA_FILES = {"profile.json", "publications.json", "broad_impact.json"}
REQUIRED_FILES = {"profile.json", "publications.json"}

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class AuthorInput:
    slug: str
    source_id: str
    name: str
    affiliation: str | None
    orcid_id: str | None
    profile: JsonObject
    publications: list[JsonObject]
    broad_impact: list[JsonObject]


@dataclass(frozen=True)
class ImportSummary:
    snapshot_id: UUID
    imported: bool
    authors: int
    publications: int
    broad_impact_records: int


def normalize_doi(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None

    return value.strip().casefold().rsplit("doi.org/", 1)[-1]


def read_json(archive: ZipFile, member: str) -> object:
    return json.loads(archive.read(member))


def dataset_members(archive: ZipFile) -> dict[str, dict[str, str]]:
    members: dict[str, dict[str, str]] = {}
    for entry in archive.infolist():
        parts = PurePosixPath(entry.filename).parts
        if entry.is_dir() or len(parts) != 3 or parts[0] != "authors":
            continue
        slug, filename = parts[1], parts[2]
        if filename not in DATA_FILES:
            continue
        author_files = members.setdefault(slug, {})
        if filename in author_files:
            raise ValueError(f"Duplicate {filename} for {slug}")
        author_files[filename] = entry.filename
    return members


def required_text(value: object, error: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(error)
    return value.strip()


def optional_text(value: object, error: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(error)
    return value.strip() or None


def read_author_input(archive: ZipFile, slug: str, files: dict[str, str]) -> AuthorInput:
    missing = REQUIRED_FILES - files.keys()
    if missing:
        raise ValueError(f"{slug} is missing {', '.join(sorted(missing))}")

    profile = read_json(archive, files["profile.json"])
    publications = read_json(archive, files["publications.json"])
    broad_impact = (
        read_json(archive, files["broad_impact.json"]) if "broad_impact.json" in files else []
    )
    if not isinstance(profile, dict):
        raise ValueError(f"{slug}/profile.json must contain an object")
    if not isinstance(publications, list) or not all(isinstance(row, dict) for row in publications):
        raise ValueError(f"{slug}/publications.json must contain a list of objects")
    if not isinstance(broad_impact, list) or not all(isinstance(row, dict) for row in broad_impact):
        raise ValueError(f"{slug}/broad_impact.json must contain a list of objects")

    source_id = required_text(profile.get("id"), f"{slug}/profile.json has no author ID")
    name = required_text(profile.get("name"), f"{slug}/profile.json has no author name")
    for publication in publications:
        required_text(
            publication.get("title"),
            f"{slug}/publications.json contains a publication without a title",
        )
    affiliation = optional_text(
        profile.get("affiliation"),
        f"{slug}/profile.json has an invalid affiliation",
    )
    orcid = profile.get("orcid")
    if orcid is not None and not isinstance(orcid, dict):
        raise ValueError(f"{slug}/profile.json has an invalid ORCID record")
    orcid_id = optional_text(
        orcid.get("orcid_id") if isinstance(orcid, dict) else None,
        f"{slug}/profile.json has an invalid ORCID identifier",
    )
    return AuthorInput(
        slug=slug,
        source_id=source_id,
        name=name,
        affiliation=affiliation,
        orcid_id=orcid_id,
        profile=profile,
        publications=publications,
        broad_impact=broad_impact,
    )


def read_dataset(archive_path: Path = AUTHORS_ARCHIVE) -> list[AuthorInput]:
    with ZipFile(archive_path) as archive:
        authors = [
            read_author_input(archive, slug, files)
            for slug, files in sorted(dataset_members(archive).items())
        ]
    if not authors:
        raise ValueError("Archive contains no author records")

    source_ids = set()
    for author in authors:
        if author.source_id in source_ids:
            raise ValueError(f"Duplicate author ID: {author.source_id}")
        source_ids.add(author.source_id)
    return authors


def archive_sha256(archive_path: Path) -> str:
    with archive_path.open("rb") as archive:
        return hashlib.file_digest(archive, "sha256").hexdigest()


def snapshot_summary(
    session: Session,
    snapshot_id: UUID,
    imported: bool,
) -> ImportSummary:
    authors = session.scalar(
        select(func.count(Author.id)).where(Author.dataset_snapshot_id == snapshot_id)
    )
    publications = session.scalar(
        select(func.count(PublicationRecord.id))
        .join(Author)
        .where(Author.dataset_snapshot_id == snapshot_id)
    )
    broad_impact_records = session.scalar(
        select(func.count(BroadImpactRecord.id))
        .join(Author)
        .where(Author.dataset_snapshot_id == snapshot_id)
    )
    return ImportSummary(
        snapshot_id=snapshot_id,
        imported=imported,
        authors=authors or 0,
        publications=publications or 0,
        broad_impact_records=broad_impact_records or 0,
    )


def import_dataset(session: Session, archive_path: Path = AUTHORS_ARCHIVE) -> ImportSummary:
    dataset_sha256 = archive_sha256(archive_path)
    existing = session.scalar(
        select(DatasetSnapshot).where(DatasetSnapshot.dataset_sha256 == dataset_sha256)
    )
    if existing is not None:
        return snapshot_summary(session, existing.id, imported=False)

    authors = read_dataset(archive_path)
    snapshot_id = uuid4()
    session.add(DatasetSnapshot(id=snapshot_id, dataset_sha256=dataset_sha256))
    session.flush()

    for author_input in authors:
        profile = author_input.profile
        author_id = uuid4()
        session.add(
            Author(
                id=author_id,
                dataset_snapshot_id=snapshot_id,
                source_id=author_input.source_id,
                slug=author_input.slug,
                name=author_input.name,
                affiliation=author_input.affiliation,
                orcid_id=author_input.orcid_id,
                profile=profile,
            )
        )

        session.add_all(
            PublicationRecord(
                author_id=author_id,
                position=position,
                normalized_doi=normalize_doi(publication.get("doi")),
                title=publication["title"].strip(),
                journal=publication.get("journal"),
                year=publication.get("year"),
                citations=publication.get("citations"),
                source=publication.get("source"),
                payload=publication,
            )
            for position, publication in enumerate(author_input.publications)
        )
        session.add_all(
            BroadImpactRecord(
                author_id=author_id,
                position=position,
                url=record.get("url"),
                category=record.get("category"),
                relevance_score=record.get("relevance_score"),
                snippet=record.get("snippet"),
                reasoning=record.get("reasoning"),
                payload=record,
            )
            for position, record in enumerate(author_input.broad_impact)
        )

    session.flush()
    return snapshot_summary(session, snapshot_id, imported=True)


def main() -> None:
    create_schema()
    with SessionFactory.begin() as session:
        summary = import_dataset(session)

    action = "Imported" if summary.imported else "Already imported"
    print(f"{action} dataset snapshot {summary.snapshot_id}")
    print(f"Authors: {summary.authors}")
    print(f"Publication records: {summary.publications}")
    print(f"Broad-impact records: {summary.broad_impact_records}")


if __name__ == "__main__":
    main()
