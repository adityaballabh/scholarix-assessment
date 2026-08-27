import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from merge_review.cases.evidence import evidence_rows
from merge_review.cases.naming import author_key
from merge_review.models import (
    Author,
    CaseEvidence,
    IdentityCandidate,
    IdentityCandidatePublication,
    PublicationRecord,
    ReviewSettings,
    SourceRecord,
    ValidationCase,
)
from merge_review.sources.common import FetchStatus

CASE_TYPE = "author_identity"
MAX_TOP_CANDIDATE_SHARE = 75.0
PRIORITY_WEIGHTS = {
    "publication_impact": 1.0,
    "fragmentation": 1.0,
    "cluster_ambiguity": 1.0,
}


@dataclass(frozen=True)
class CandidatePublication:
    doi: str
    title: str
    year: int | None
    source_record_id: UUID


@dataclass(frozen=True)
class Candidate:
    semantic_scholar_author_id: str
    publications: tuple[CandidatePublication, ...]
    share: float
    first_year: int | None
    last_year: int | None


@dataclass(frozen=True)
class IdentityCaseData:
    author: Author
    candidates: list[Candidate]
    affected_count: int
    semantic_scholar_records: dict[str, SourceRecord]

    @property
    def fragmentation(self) -> float:
        return round(100.0 - self.candidates[0].share, 1)


@dataclass(frozen=True)
class PriorityMaximums:
    publication_impact: float
    fragmentation: float
    cluster_ambiguity: float


@dataclass(frozen=True)
class CandidateInputs:
    affected_count: int
    publications_by_doi: dict[str, PublicationRecord]
    semantic_scholar_records: dict[str, SourceRecord]


def case_id(snapshot_id: UUID, slug: str) -> str:
    digest = hashlib.sha1(f"identity|{snapshot_id}|{slug}".encode()).hexdigest()
    return "c-" + digest[:10]


def requires_identity_review(candidates: list[Candidate]) -> bool:
    return bool(candidates) and candidates[0].share <= MAX_TOP_CANDIDATE_SHARE


def default_review_settings(snapshot_id: UUID) -> ReviewSettings:
    return ReviewSettings(
        dataset_snapshot_id=snapshot_id,
        max_top_candidate_share=MAX_TOP_CANDIDATE_SHARE,
        priority_weights=PRIORITY_WEIGHTS.copy(),
        version=1,
    )


def get_or_create_review_settings(session: Session, snapshot_id: UUID) -> ReviewSettings:
    settings = session.get(ReviewSettings, snapshot_id)
    if settings is None:
        settings = default_review_settings(snapshot_id)
        session.add(settings)
        session.flush()
    return settings


def normalized_component(value: float, snapshot_max: float) -> float:
    return round(100.0 * value / snapshot_max, 1) if snapshot_max else 0.0


def score_values(
    data: IdentityCaseData,
    maximums: PriorityMaximums,
    weights: dict[str, float] | None = None,
    max_top_candidate_share: float = MAX_TOP_CANDIDATE_SHARE,
) -> tuple[float, dict[str, dict[str, float]], dict[str, Any]]:
    weights = weights or PRIORITY_WEIGHTS
    raw_values = {
        "publication_impact": float(data.affected_count),
        "fragmentation": data.fragmentation,
        "cluster_ambiguity": float(len(data.candidates)),
    }
    snapshot_maximums = {
        "publication_impact": maximums.publication_impact,
        "fragmentation": maximums.fragmentation,
        "cluster_ambiguity": maximums.cluster_ambiguity,
    }
    components = {
        name: {
            "value": value,
            "snapshot_max": snapshot_maximums[name],
            "score": normalized_component(value, snapshot_maximums[name]),
        }
        for name, value in raw_values.items()
    }
    weight_total = sum(weights.values())
    normalized_weights = {name: weight / weight_total for name, weight in weights.items()}
    score = round(
        sum(components[name]["score"] * normalized_weights[name] for name in normalized_weights),
        1,
    )
    config = {
        "weights": normalized_weights,
        "max_top_candidate_share": max_top_candidate_share,
    }
    return score, components, config


def load_candidate_inputs(session: Session, author: Author) -> CandidateInputs:
    publications = list(
        session.scalars(
            select(PublicationRecord)
            .where(PublicationRecord.author_id == author.id)
            .order_by(PublicationRecord.position)
        )
    )
    distinct_dois = {
        publication.normalized_doi for publication in publications if publication.normalized_doi
    }
    no_doi_count = sum(publication.normalized_doi is None for publication in publications)
    affected_count = len(distinct_dois) + no_doi_count
    publications_by_doi = {
        publication.normalized_doi: publication
        for publication in publications
        if publication.normalized_doi
    }
    if not publications_by_doi:
        return CandidateInputs(affected_count, {}, {})

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
    semantic_scholar_records = {record.entity_key: record for record in source_records}
    return CandidateInputs(affected_count, publications_by_doi, semantic_scholar_records)


def build_candidates(author_name: str, inputs: CandidateInputs) -> list[Candidate]:
    matched: dict[str, dict[str, CandidatePublication]] = defaultdict(dict)
    expected_key = author_key(author_name)

    for doi, source_record in inputs.semantic_scholar_records.items():
        payload = source_record.payload
        if not isinstance(payload, dict):
            continue
        stored_publication = inputs.publications_by_doi[doi]
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
                semantic_scholar_author_id=external_author_id,
                publications=candidate_rows,
                share=round(100 * len(candidate_rows) / total_matches, 1),
                first_year=min(years) if years else None,
                last_year=max(years) if years else None,
            )
        )
    candidates.sort(
        key=lambda candidate: (
            -len(candidate.publications),
            candidate.semantic_scholar_author_id,
        )
    )
    return candidates


def clear_case_details(session: Session, case_id_value: str) -> None:
    candidate_ids = select(IdentityCandidate.id).where(IdentityCandidate.case_id == case_id_value)
    session.execute(
        delete(IdentityCandidatePublication).where(
            IdentityCandidatePublication.identity_candidate_id.in_(candidate_ids)
        )
    )
    session.execute(delete(IdentityCandidate).where(IdentityCandidate.case_id == case_id_value))
    session.execute(delete(CaseEvidence).where(CaseEvidence.case_id == case_id_value))


def case_signature(
    data: IdentityCaseData,
    evidence: list[dict[str, Any]],
    score: float,
    components: dict[str, dict[str, float]],
    config: dict[str, Any],
) -> str:
    content = {
        "candidates": [
            {
                "author_id": candidate.semantic_scholar_author_id,
                "share": candidate.share,
                "first_year": candidate.first_year,
                "last_year": candidate.last_year,
                "publications": [
                    {
                        "doi": publication.doi,
                        "title": publication.title,
                        "year": publication.year,
                        "source_record_id": str(publication.source_record_id),
                    }
                    for publication in candidate.publications
                ],
            }
            for candidate in data.candidates
        ],
        # Fetch time alone does not change the evidence a reviewer saw
        "evidence": [
            {key: value for key, value in row.items() if key != "fetched_at"} for row in evidence
        ],
        "score": score,
        "components": components,
        "config": config,
    }
    serialized = json.dumps(content, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


def generate_identity_case(
    session: Session,
    data: IdentityCaseData,
    maximums: PriorityMaximums,
    settings: ReviewSettings,
) -> ValidationCase:
    author = data.author
    candidates = data.candidates
    affected_count = data.affected_count
    semantic_scholar_records = data.semantic_scholar_records
    case_id_value = case_id(author.dataset_snapshot_id, author.slug)
    review_case = session.get(ValidationCase, case_id_value)
    score, components, config = score_values(
        data,
        maximums,
        settings.priority_weights,
        settings.max_top_candidate_share,
    )
    evidence = evidence_rows(session, author, candidates, semantic_scholar_records)
    signature = case_signature(data, evidence, score, components, config)
    if review_case is None:
        review_case = ValidationCase(
            id=case_id_value,
            dataset_snapshot_id=author.dataset_snapshot_id,
            author_id=author.id,
            case_type=CASE_TYPE,
            queue_eligible=True,
            priority_score=score,
            priority_components=components,
            priority_config=config,
            evidence_sha256=signature,
            affected_count=affected_count,
        )
        session.add(review_case)
    else:
        clear_case_details(session, case_id_value)
        if not review_case.queue_eligible or review_case.evidence_sha256 != signature:
            review_case.version += 1
        review_case.queue_eligible = True
        review_case.priority_score = score
        review_case.priority_components = components
        review_case.priority_config = config
        review_case.evidence_sha256 = signature
        review_case.affected_count = affected_count
    session.flush()

    for position, row in enumerate(evidence):
        session.add(CaseEvidence(case_id=case_id_value, position=position, **row))

    for position, candidate in enumerate(candidates):
        candidate_id = uuid4()
        session.add(
            IdentityCandidate(
                id=candidate_id,
                case_id=case_id_value,
                position=position,
                semantic_scholar_author_id=candidate.semantic_scholar_author_id,
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


def generate_identity_cases(session: Session, snapshot_id: UUID) -> int:
    settings = get_or_create_review_settings(session, snapshot_id)
    authors = session.scalars(
        select(Author).where(Author.dataset_snapshot_id == snapshot_id).order_by(Author.name)
    )
    case_data = []
    for author in authors:
        inputs = load_candidate_inputs(session, author)
        candidates = build_candidates(author.name, inputs)
        if candidates and candidates[0].share <= settings.max_top_candidate_share:
            case_data.append(
                IdentityCaseData(
                    author,
                    candidates,
                    inputs.affected_count,
                    inputs.semantic_scholar_records,
                )
            )
            continue
        review_case = session.get(
            ValidationCase,
            case_id(author.dataset_snapshot_id, author.slug),
        )
        if review_case is not None and review_case.queue_eligible:
            review_case.queue_eligible = False
            review_case.version += 1

    maximums = PriorityMaximums(
        publication_impact=max((data.affected_count for data in case_data), default=0),
        fragmentation=max((data.fragmentation for data in case_data), default=0.0),
        cluster_ambiguity=max((len(data.candidates) for data in case_data), default=0),
    )
    for data in case_data:
        generate_identity_case(session, data, maximums, settings)
    return len(case_data)
