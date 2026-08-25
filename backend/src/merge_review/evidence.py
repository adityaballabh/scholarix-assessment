from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from merge_review.models import Author, SourceRecord
from merge_review.naming import institutions_match, normalized_words
from merge_review.sources.common import FetchStatus

if TYPE_CHECKING:
    from merge_review.generate_cases import Candidate


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


def semantic_scholar_evidence(
    candidates: list[Candidate],
    s2_records: dict[str, SourceRecord],
) -> dict[str, Any]:
    matched_s2_records = {
        publication.source_record_id
        for candidate in candidates
        for publication in candidate.publications
    }
    fetched_at = max(
        (record.fetched_at for record in s2_records.values() if record.id in matched_s2_records),
        default=None,
    )
    return {
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


def openalex_evidence(session: Session, author: Author) -> list[dict[str, Any]]:
    record = source_record(
        session,
        author.dataset_snapshot_id,
        "openalex",
        "author",
        author.source_id,
    )
    payload = record.payload if record else None
    external_name = payload.get("display_name") if isinstance(payload, dict) else None
    external_affiliation = openalex_institution(payload)
    return [
        source_evidence(
            record,
            "openalex",
            author.source_id,
            "canonical_name",
            external_name,
            "supports"
            if normalized_words(external_name) == normalized_words(author.name)
            else "conflict",
        ),
        source_evidence(
            record,
            "openalex",
            author.source_id,
            "affiliation",
            external_affiliation,
            "supports"
            if institutions_match(external_affiliation, author.affiliation)
            else "conflict",
        ),
    ]


def orcid_evidence(session: Session, author: Author) -> dict[str, Any]:
    record = (
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
    institutions = orcid_institutions(record.payload if record else None)
    institution_value = "; ".join(institutions) or None
    if not author.orcid_id:
        institution_state = "missing"
    elif record is None or record.fetch_status != FetchStatus.SUCCESS:
        institution_state = "unverifiable"
    elif not institutions:
        institution_state = "missing"
    else:
        institution_state = (
            "supports"
            if any(
                institutions_match(author.affiliation, institution) for institution in institutions
            )
            else "conflict"
        )
    return source_evidence(
        record,
        "orcid",
        author.orcid_id,
        "affiliation",
        institution_value,
        institution_state,
    )


def evidence_rows(
    session: Session,
    author: Author,
    candidates: list[Candidate],
    s2_records: dict[str, SourceRecord],
) -> list[dict[str, Any]]:
    rows = [semantic_scholar_evidence(candidates, s2_records)]
    rows.extend(openalex_evidence(session, author))
    rows.append(orcid_evidence(session, author))
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
        if source_id:
            raise RuntimeError(f"Missing {source} record for {source_id}")
        fetch_status = FetchStatus.NOT_APPLICABLE
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
