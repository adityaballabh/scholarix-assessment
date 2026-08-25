export type SourceFetchStatus =
  | "success"
  | "pending"
  | "not_applicable"
  | "empty"
  | "not_found"
  | "rate_limited"
  | "timeout"
  | "error";

export type EvidenceValueState =
  | "supports"
  | "conflict"
  | "missing"
  | "unverifiable";
export type SourceHealthState =
  | "available"
  | "partially_available"
  | "unavailable";

export type ReviewStatus =
  | "pending"
  | "deferred"
  | "uncertain"
  | "one_author"
  | "needs_split";

export type QueueScope = "active" | "archived";
export type RefreshSource = "openalex" | "semantic_scholar" | "orcid";
export type EvidenceEntityType = "author" | "publication";

export interface SourceRecordReference {
  entity_type: EvidenceEntityType;
  id: string;
}

export interface EvidenceRecord {
  source: string;
  source_refs: SourceRecordReference[];
  fetched_at: string | null;
  fetch_status: SourceFetchStatus;
  field: string;
  value: string | null;
  value_state: EvidenceValueState;
  interpretation: string;
}

export interface SemanticScholarCandidate {
  id: string;
  share: number;
  first_year: number | null;
  last_year: number | null;
  publications: ClusterPublication[];
}

export interface ClusterPublication {
  year: number | null;
  title: string;
}

export interface AuthorIdentityDetail {
  candidate_ids: SemanticScholarCandidate[];
  top_share: number | null;
  openalex_topics: string[];
}

export interface ReviewTarget {
  author_slug: string;
  author_name: string;
  openalex_id: string | null;
}

export interface ValidationCase {
  id: string;
  status: ReviewStatus;
  queue_eligible: boolean;
  priority_score: number;
  priority_components: PriorityComponents;
  priority_config: PriorityConfig;
  target: ReviewTarget;
  affected_count: number;
  version: number;
  evidence: EvidenceRecord[];
  detail: AuthorIdentityDetail;
}

export interface PriorityComponent {
  value: number;
  snapshot_max: number;
  score: number;
}

export interface PriorityComponents {
  publication_impact: PriorityComponent;
  fragmentation: PriorityComponent;
  cluster_ambiguity: PriorityComponent;
}

export interface PriorityWeights {
  publication_impact: number;
  fragmentation: number;
  cluster_ambiguity: number;
}

export interface PriorityConfig {
  weights: PriorityWeights;
  max_top_candidate_share: number;
}

export interface QueueSettings {
  max_top_candidate_share: number;
  weights: PriorityWeights;
  version: number;
  updated_at: string | null;
}

export interface QueueSettingsUpdate {
  max_top_candidate_share: number;
  weights: PriorityWeights;
  expected_version: number;
}

export interface QueueRebuildResult {
  config_version: number;
  cases: number;
}

export interface RefreshResult {
  scope: "author" | "author_source" | "doi" | "source";
  target: string;
  results: Record<string, number>;
  cases: number;
}

export type DecisionAction =
  | "reopen"
  | "confirm_one_author"
  | "flag_for_split"
  | "mark_uncertain"
  | "defer"
  | "note";

export interface DecisionRequest {
  case_id: string;
  action: DecisionAction;
  note?: string;
  expected_version: number;
}

export interface ActivityEvent {
  id: string;
  case_id: string;
  action_type: DecisionAction;
  actor: string;
  created_at: string;
  target_name: string;
  note: string | null;
  before: ReviewStatus | null;
  after: ReviewStatus | null;
}

export interface SourceStatus {
  source: string;
  fetched_at: string | null;
  state: SourceHealthState;
  note: string;
}

export interface ReviewOverview {
  flagged_authors: number;
  affected_publications: number;
  total_authors: number;
  total_publications: number;
  queue_updated_at: string | null;
  sources: SourceStatus[];
}

export interface CaseQueryFilters {
  status?: ReviewStatus | ReviewStatus[];
  scope?: QueueScope;
  query?: string;
}

export type FetchRunStatus =
  | "queued"
  | "running"
  | "complete"
  | "failed"
  | "abandoned";

export interface FetchSourceProgress {
  completed: number;
  total: number;
  by_status: Record<string, number>;
  completed_at?: string | null;
}

export interface FetchRun {
  id: string;
  status: FetchRunStatus;
  current_source: string | null;
  source_progress: Record<string, FetchSourceProgress>;
  started_at: string | null;
  finished_at: string | null;
  last_completed_at: string | null;
  error: string | null;
}
