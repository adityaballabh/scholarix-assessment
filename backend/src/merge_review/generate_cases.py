import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from unidecode import unidecode

from merge_review.database import SessionFactory, create_schema
from merge_review.models import (
    Author,
    CaseEvidence,
    DatasetSnapshot,
    IdentityCandidate,
    IdentityCandidatePublication,
    PublicationRecord,
    SourceRecord,
    ValidationCase,
)
from merge_review.source_records import FetchStatus

CASE_TYPE = "author_identity"
HIGH_PRIORITY_CANDIDATE_THRESHOLD = 11
MAX_TOP_CANDIDATE_SHARE = 75.0


@dataclass(frozen=True)
class CandidatePublication:
    doi: str
    title: str
    year: int | None
    source_record_id: UUID


@dataclass(frozen=True)
class Candidate:
    author_id: str
    publications: tuple[CandidatePublication, ...]
    share: float
    first_year: int | None
    last_year: int | None


def normalized_words(value: str | None) -> list[str]:
    return re.findall(r"[a-z0-9]+", unidecode(value or "").lower())


def author_key(value: str | None) -> str | None:
    words = normalized_words(value)
    if len(words) == 1:
        return words[0]
    return f"{words[-1]} {words[0][0]}" if words else None


def normalized_institution(value: str | None) -> str:
    return " ".join(normalized_words(value))


def case_id(slug: str) -> str:
    digest = hashlib.sha1(f"identity|{slug}".encode()).hexdigest()
    return "c-" + digest[:10]


def requires_identity_review(candidates: list[Candidate]) -> bool:
    return bool(candidates) and candidates[0].share <= MAX_TOP_CANDIDATE_SHARE


def candidate_publications(
    session: Session,
    author: Author,
) -> tuple[list[Candidate], list[PublicationRecord], dict[str, SourceRecord]]:
    publications = list(
        session.scalars(
            select(PublicationRecord)
            .where(PublicationRecord.author_id == author.id)
            .order_by(PublicationRecord.position)
        )
    )
    publications_by_doi = {
        publication.normalized_doi: publication
        for publication in publications
        if publication.normalized_doi
    }
    if not publications_by_doi:
        return [], publications, {}

    source_records = list(
        session.scalars(
            select(SourceRecord).where(
                SourceRecord.dataset_snapshot_id == author.dataset_snapshot_id,
                SourceRecord.source == "semantic_scholar",
                SourceRecord.entity_type == "publication",
                SourceRecord.entity_key.in_(publications_by_doi),
                SourceRecord.fetch_status == FetchStatus.SUCCESS,
            )
        )
    )
    source_records_by_doi = {record.entity_key: record for record in source_records}
    matched: dict[str, dict[str, CandidatePublication]] = defaultdict(dict)
    expected_key = author_key(author.name)

    for doi, source_record in source_records_by_doi.items():
        payload = source_record.payload
        if not isinstance(payload, dict):
            continue
        stored_publication = publications_by_doi[doi]
        title = payload.get("title") or stored_publication.title
        year = payload.get("year")
        if not isinstance(year, int):
            year = stored_publication.year

        for external_author in payload.get("authors") or []:
            if not isinstance(external_author, dict):
                continue
            external_author_id = external_author.get("authorId")
            if (
                isinstance(external_author_id, str)
                and external_author_id
                and author_key(external_author.get("name")) == expected_key
            ):
                matched[external_author_id][doi] = CandidatePublication(
                    doi=doi,
                    title=title,
                    year=year,
                    source_record_id=source_record.id,
                )

    total_matches = sum(len(rows) for rows in matched.values())
    candidates = []
    for external_author_id, rows in matched.items():
        candidate_rows = tuple(
            sorted(
                rows.values(),
                key=lambda row: (row.year is None, -(row.year or 0), row.title),
            )
        )
        years = [row.year for row in candidate_rows if row.year is not None]
        candidates.append(
            Candidate(
                author_id=external_author_id,
                publications=candidate_rows,
                share=round(100 * len(candidate_rows) / total_matches, 1),
                first_year=min(years) if years else None,
                last_year=max(years) if years else None,
            )
        )
    candidates.sort(key=lambda candidate: (-len(candidate.publications), candidate.author_id))
    return candidates, publications, source_records_by_doi


def source_record(
    session: Session,
    snapshot_id: UUID,
    source: str,
    entity_type: str,
    entity_key: str,
) -> SourceRecord | None:
    return session.scalar(
        select(SourceRecord).where(
            SourceRecord.dataset_snapshot_id == snapshot_id,
            SourceRecord.source == source,
            SourceRecord.entity_type == entity_type,
            SourceRecord.entity_key == entity_key,
        )
    )


def openalex_institution(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    institutions = payload.get("last_known_institutions") or []
    for institution in institutions:
        if isinstance(institution, dict) and institution.get("display_name"):
            return institution["display_name"]
    return None


def orcid_institutions(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    activities = payload.get("activities-summary") or {}
    employments = activities.get("employments") or {}
    institutions = []
    for group in employments.get("affiliation-group") or []:
        for row in group.get("summaries") or []:
            summary = row.get("employment-summary") or {}
            name = (summary.get("organization") or {}).get("name")
            if name and name not in institutions:
                institutions.append(name)
    return institutions


def evidence_rows(
    session: Session,
    author: Author,
    candidates: list[Candidate],
    s2_records: dict[str, SourceRecord],
) -> list[dict[str, Any]]:
    matched_s2_records = {
        publication.source_record_id
        for candidate in candidates
        for publication in candidate.publications
    }
    fetched_at = max(
        (record.fetched_at for record in s2_records.values() if record.id in matched_s2_records),
        default=None,
    )
    rows = [
        {
            "source": "semantic_scholar",
            "source_record_ids": [str(record_id) for record_id in sorted(matched_s2_records)],
            "source_refs": [
                {"entity_type": "author", "id": candidate.author_id} for candidate in candidates
            ],
            "fetched_at": fetched_at,
            "fetch_status": FetchStatus.SUCCESS,
            "field": "author_identity",
            "value": f"{len(candidates)} S2 IDs for publications matching this name",
            "value_state": "conflict",
            "interpretation": (
                "Publications under the stored name map to multiple Semantic Scholar author "
                "IDs. This is a review signal, not a merge determination."
            ),
        }
    ]

    openalex = source_record(
        session,
        author.dataset_snapshot_id,
        "openalex",
        "author",
        author.source_id,
    )
    openalex_payload = openalex.payload if openalex else None
    external_name = (
        openalex_payload.get("display_name") if isinstance(openalex_payload, dict) else None
    )
    external_affiliation = openalex_institution(openalex_payload)
    rows.extend(
        [
            source_evidence(
                openalex,
                "openalex",
                author.source_id,
                "canonical_name",
                external_name,
                "supports"
                if normalized_words(external_name) == normalized_words(author.name)
                else "conflict",
            ),
            source_evidence(
                openalex,
                "openalex",
                author.source_id,
                "affiliation",
                external_affiliation,
                "supports"
                if normalized_institution(external_affiliation)
                == normalized_institution(author.affiliation)
                else "conflict",
            ),
        ]
    )

    orcid = (
        source_record(
            session,
            author.dataset_snapshot_id,
            "orcid",
            "author",
            author.orcid_id,
        )
        if author.orcid_id
        else None
    )
    institutions = orcid_institutions(orcid.payload if orcid else None)
    institution_value = "; ".join(institutions) or None
    if not author.orcid_id:
        orcid_state = "missing"
    elif orcid is None or orcid.fetch_status != FetchStatus.SUCCESS:
        orcid_state = "unverifiable"
    elif not institutions:
        orcid_state = "missing"
    else:
        orcid_state = (
            "supports"
            if normalized_institution(author.affiliation)
            in {normalized_institution(institution) for institution in institutions}
            else "conflict"
        )
    rows.append(
        source_evidence(
            orcid,
            "orcid",
            author.orcid_id,
            "affiliation",
            institution_value,
            orcid_state,
        )
    )
    return rows


def source_evidence(
    record: SourceRecord | None,
    source: str,
    source_id: str | None,
    field: str,
    value: str | None,
    value_state: str,
) -> dict[str, Any]:
    if record is None:
        fetch_status = FetchStatus.NEVER_ATTEMPTED
    else:
        fetch_status = record.fetch_status
    if fetch_status != FetchStatus.SUCCESS:
        value_state = "unverifiable" if source_id else "missing"
        value = None
    elif value is None:
        value_state = "missing"

    return {
        "source": source,
        "source_record_ids": [str(record.id)] if record else [],
        "source_refs": [{"entity_type": "author", "id": source_id}] if source_id else [],
        "fetched_at": record.fetched_at if record else None,
        "fetch_status": fetch_status,
        "field": field,
        "value": value,
        "value_state": value_state,
        "interpretation": "",
    }


def clear_case_details(session: Session, case_id_value: str) -> None:
    candidate_ids = select(IdentityCandidate.id).where(IdentityCandidate.case_id == case_id_value)
    session.execute(
        delete(IdentityCandidatePublication).where(
            IdentityCandidatePublication.identity_candidate_id.in_(candidate_ids)
        )
    )
    session.execute(delete(IdentityCandidate).where(IdentityCandidate.case_id == case_id_value))
    session.execute(delete(CaseEvidence).where(CaseEvidence.case_id == case_id_value))


def generate_identity_case(
    session: Session,
    author: Author,
) -> ValidationCase | None:
    candidates, publications, s2_records = candidate_publications(session, author)
    case_id_value = case_id(author.slug)
    review_case = session.get(ValidationCase, case_id_value)

    if not requires_identity_review(candidates):
        if review_case is not None and review_case.status == "pending":
            clear_case_details(session, case_id_value)
            session.delete(review_case)
        return None

    priority = "high" if len(candidates) >= HIGH_PRIORITY_CANDIDATE_THRESHOLD else "medium"
    if review_case is None:
        review_case = ValidationCase(
            id=case_id_value,
            dataset_snapshot_id=author.dataset_snapshot_id,
            author_id=author.id,
            case_type=CASE_TYPE,
            priority=priority,
            affected_count=len(publications),
        )
        session.add(review_case)
    else:
        clear_case_details(session, case_id_value)
        review_case.priority = priority
        review_case.affected_count = len(publications)
    session.flush()

    for position, row in enumerate(evidence_rows(session, author, candidates, s2_records)):
        session.add(CaseEvidence(case_id=case_id_value, position=position, **row))

    for position, candidate in enumerate(candidates):
        candidate_id = uuid4()
        session.add(
            IdentityCandidate(
                id=candidate_id,
                case_id=case_id_value,
                position=position,
                semantic_scholar_author_id=candidate.author_id,
                matched_publication_count=len(candidate.publications),
                share=candidate.share,
                first_year=candidate.first_year,
                last_year=candidate.last_year,
            )
        )
        session.add_all(
            IdentityCandidatePublication(
                identity_candidate_id=candidate_id,
                position=publication_position,
                doi=publication.doi,
                title=publication.title,
                year=publication.year,
                source_record_id=publication.source_record_id,
            )
            for publication_position, publication in enumerate(candidate.publications)
        )
    session.flush()
    return review_case


def generate_identity_cases(session: Session, snapshot_id: UUID) -> dict[str, int]:
    authors = session.scalars(
        select(Author).where(Author.dataset_snapshot_id == snapshot_id).order_by(Author.name)
    )
    counts = {"high": 0, "medium": 0}
    for author in authors:
        review_case = generate_identity_case(session, author)
        if review_case is not None:
            counts[review_case.priority] += 1
    return counts


def main() -> None:
    create_schema()
    with SessionFactory.begin() as session:
        snapshot = session.scalar(
            select(DatasetSnapshot).order_by(DatasetSnapshot.imported_at.desc()).limit(1)
        )
        if snapshot is None:
            raise RuntimeError("Import a dataset before generating cases")
        counts = generate_identity_cases(session, snapshot.id)

    print(f"Identity cases for snapshot {snapshot.id}")
    print(f"High priority: {counts['high']}")
    print(f"Medium priority: {counts['medium']}")


if __name__ == "__main__":
    main()
