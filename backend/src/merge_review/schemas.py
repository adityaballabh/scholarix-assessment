from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

SourceFetchStatus = Literal[
    "success",
    "pending",
    "not_applicable",
    "empty",
    "not_found",
    "rate_limited",
    "timeout",
    "error",
]
EvidenceValueState = Literal["supports", "conflict", "missing", "unverifiable"]
SourceHealthState = Literal["available", "partially_available", "unavailable"]
ReviewStatus = Literal["pending", "deferred", "uncertain", "one_author", "needs_split"]
QueueScope = Literal["active", "archived"]
RefreshSource = Literal[
    "openalex",
    "semantic_scholar",
    "orcid",
]
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
    openalex_topics: list[str]


class ReviewTarget(BaseModel):
    author_slug: str
    author_name: str
    openalex_id: str | None


class PriorityComponent(BaseModel):
    value: float
    snapshot_max: float
    score: float


class PriorityComponents(BaseModel):
    publication_impact: PriorityComponent
    fragmentation: PriorityComponent
    cluster_ambiguity: PriorityComponent


class PriorityConfig(BaseModel):
    weights: dict[str, float]
    max_top_candidate_share: float


class PriorityWeights(BaseModel):
    publication_impact: float = Field(ge=0)
    fragmentation: float = Field(ge=0)
    cluster_ambiguity: float = Field(ge=0)

    @model_validator(mode="after")
    def require_positive_total(self) -> "PriorityWeights":
        if sum(self.model_dump().values()) <= 0:
            raise ValueError("At least one priority weight must be positive")
        return self


class QueueSettingsUpdate(BaseModel):
    max_top_candidate_share: float = Field(ge=0, le=100)
    weights: PriorityWeights
    expected_version: int = Field(ge=1)


class QueueSettingsResponse(BaseModel):
    max_top_candidate_share: float
    weights: PriorityWeights
    version: int
    updated_at: datetime | None


class RefreshResponse(BaseModel):
    scope: Literal["author", "author_source", "doi", "source"]
    target: str
    results: dict[str, int]
    cases: int


class FetchSourceProgress(BaseModel):
    completed: int
    total: int
    by_status: dict[str, int]
    completed_at: datetime | None = None


class FetchRunResponse(BaseModel):
    id: str
    status: Literal["queued", "running", "complete", "failed", "abandoned"]
    current_source: str | None
    source_progress: dict[str, FetchSourceProgress]
    started_at: datetime | None
    finished_at: datetime | None
    last_completed_at: datetime | None
    error: str | None


class QueueRebuildResponse(BaseModel):
    config_version: int
    cases: int


class ValidationCaseResponse(BaseModel):
    id: str
    status: ReviewStatus
    queue_eligible: bool
    priority_score: float
    priority_components: PriorityComponents
    priority_config: PriorityConfig
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
    state: SourceHealthState
    note: str


class ReviewOverview(BaseModel):
    flagged_authors: int
    affected_publications: int
    total_authors: int
    total_publications: int
    queue_updated_at: datetime | None
    sources: list[SourceStatus]
