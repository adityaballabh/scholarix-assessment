from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SourceFetchStatus = Literal[
    "success",
    "pending",
    "never_attempted",
    "empty",
    "not_found",
    "rate_limited",
    "timeout",
    "error",
]
EvidenceValueState = Literal["supports", "conflict", "missing", "unverifiable"]
ReviewStatus = Literal["pending", "deferred", "uncertain", "one_author", "needs_split"]
CasePriority = Literal["high", "medium", "low"]
DecisionAction = Literal[
    "reopen",
    "confirm_one_author",
    "flag_for_split",
    "mark_uncertain",
    "defer",
    "note",
]


class SourceRecordReference(BaseModel):
    entity_type: Literal["author", "publication"]
    id: str


class EvidenceRecord(BaseModel):
    source: str
    source_refs: list[SourceRecordReference]
    fetched_at: datetime | None
    fetch_status: SourceFetchStatus
    field: str
    value: str | None
    value_state: EvidenceValueState
    interpretation: str


class ClusterPublication(BaseModel):
    year: int | None
    title: str


class SemanticScholarCandidate(BaseModel):
    id: str
    share: float
    first_year: int | None
    last_year: int | None
    publications: list[ClusterPublication]


class AuthorIdentityDetail(BaseModel):
    candidate_ids: list[SemanticScholarCandidate]
    top_share: float | None
    profile_topics: list[str]


class ReviewTarget(BaseModel):
    author_slug: str
    author_name: str
    openalex_id: str | None


class ValidationCaseResponse(BaseModel):
    id: str
    status: ReviewStatus
    priority: CasePriority
    target: ReviewTarget
    affected_count: int
    version: int
    evidence: list[EvidenceRecord]
    detail: AuthorIdentityDetail


class DecisionRequest(BaseModel):
    action: DecisionAction
    note: str | None = None
    expected_version: int = Field(ge=1)

    @field_validator("note")
    @classmethod
    def trim_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class ActivityEventResponse(BaseModel):
    id: str
    case_id: str
    action_type: DecisionAction
    actor: str
    created_at: datetime
    target_name: str
    note: str | None
    before: str | None
    after: str | None


class SourceStatus(BaseModel):
    source: str
    fetched_at: datetime | None
    state: SourceFetchStatus
    note: str


class ReviewOverview(BaseModel):
    authors: int
    publications: int
    authors_audited: int
    publications_audited: int
    audited_at: datetime | None
    by_priority: dict[str, int]
    sources: list[SourceStatus]
