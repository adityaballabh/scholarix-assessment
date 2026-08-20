export type SourceFetchStatus =
  | "success"
  | "pending"
  | "never_attempted"
  | "empty"
  | "not_found"
  | "rate_limited"
  | "timeout"
  | "error";

export type EvidenceValueState =
  | "supports"
  | "candidate"
  | "conflict"
  | "missing"
  | "absent"
  | "unverifiable"
  | "override";

export type ReviewStatus =
  | "pending"
  | "in_review"
  | "deferred"
  | "resolved"
  | "reopened";

export type CasePriority = "high" | "medium" | "low";
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
  profile_topics: string[];
}

export interface ReviewTarget {
  author_slug: string;
  author_name: string;
  openalex_id: string | null;
}

export interface ValidationCase {
  id: string;
  status: ReviewStatus;
  priority: CasePriority;
  target: ReviewTarget;
  affected_count: number;
  evidence: EvidenceRecord[];
  detail: AuthorIdentityDetail;
}

export type DecisionAction =
  | "confirm_one_author"
  | "flag_for_split"
  | "mark_uncertain"
  | "defer"
  | "note";

export interface DecisionRequest {
  case_id: string;
  action: DecisionAction;
  note?: string;
  resolved?: Record<string, string>;
}

export interface ActivityEvent {
  id: string;
  case_id: string;
  action_type: DecisionAction;
  actor: string;
  created_at: string;
  target_name: string;
  note: string | null;
  before: string | null;
  after: string | null;
  supersedes_event_id: string | null;
}

export interface SourceStatus {
  source: string;
  fetched_at: string | null;
  state: SourceFetchStatus;
  note: string;
}

export interface ReviewOverview {
  authors: number;
  publications: number;
  authors_audited: number;
  publications_audited: number;
  audited_at: string | null;
  open_cases: number;
  by_priority: Partial<Record<CasePriority, number>>;
  sources: SourceStatus[];
}

export interface CaseQueryFilters {
  status?: ReviewStatus | ReviewStatus[];
  priority?: CasePriority;
  query?: string;
}
