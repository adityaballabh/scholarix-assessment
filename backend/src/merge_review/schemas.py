from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

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
SourceHealthState = Literal["available", "partially_available", "unavailable"]
ReviewStatus = Literal["pending", "deferred", "uncertain", "one_author", "needs_split"]
CasePriority = Literal["very_high", "high", "medium", "low", "very_low"]
QueueScope = Literal["active", "archived"]
RefreshSource = Literal[
    "openalex",
    "crossref",
    "datacite",
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
    profile_topics: list[str]


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
    band_minimums: dict[str, float]
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


class PriorityBandMinimums(BaseModel):
    very_low: float = Field(default=0, ge=0, le=100)
    low: float = Field(ge=0, le=100)
    medium: float = Field(ge=0, le=100)
    high: float = Field(ge=0, le=100)
    very_high: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def require_ordered_bands(self) -> "PriorityBandMinimums":
        values = list(self.model_dump().values())
        if self.very_low != 0 or values != sorted(set(values)):
            raise ValueError("Priority band minimums must start at 0 and increase")
        return self


class AuditConfigUpdate(BaseModel):
    max_top_candidate_share: float = Field(ge=0, le=100)
    weights: PriorityWeights
    band_minimums: PriorityBandMinimums
    expected_version: int = Field(ge=1)


class AuditConfigResponse(BaseModel):
    max_top_candidate_share: float
    weights: PriorityWeights
    band_minimums: PriorityBandMinimums
    version: int
    updated_at: datetime | None


class RefreshResponse(BaseModel):
    scope: Literal["author", "doi", "source"]
    target: str
    results: dict[str, int]
    cases: dict[str, int]


class AuditSourceProgress(BaseModel):
    completed: int
    total: int
    by_status: dict[str, int]


class AuditRunResponse(BaseModel):
    id: str
    status: Literal["queued", "running", "complete", "failed", "abandoned"]
    current_source: str | None
    source_progress: dict[str, AuditSourceProgress]
    started_at: datetime | None
    finished_at: datetime | None
    last_completed_at: datetime | None
    error: str | None


class AuditResponse(BaseModel):
    config_version: int
    cases: dict[CasePriority, int]


class ValidationCaseResponse(BaseModel):
    id: str
    status: ReviewStatus
    queue_eligible: bool
    priority: CasePriority
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
    authors: int
    publications: int
    authors_audited: int
    publications_audited: int
    audited_at: datetime | None
    by_priority: dict[str, int]
    sources: list[SourceStatus]
