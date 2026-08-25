import type {
  ActivityEvent,
  FetchRun,
  QueueSettings,
  ReviewOverview,
  User,
  ValidationCase,
} from "../api/types";

export const CASE_ID = "case-eric-larson";
export const SECOND_CASE_ID = "case-boxuan-zhao";
export const AUTHOR_NAME = "Eric R. Larson";
export const REVIEWER: User = {
  id: "reviewer-one",
  username: "reviewer",
  display_name: "Test Reviewer",
};

export function buildReviewCase(
  overrides: Partial<ValidationCase> = {},
): ValidationCase {
  return {
    id: CASE_ID,
    dataset_imported_at: "2026-08-24T12:00:00Z",
    status: "pending",
    queue_eligible: true,
    priority_score: 76.7,
    priority_components: {
      publication_impact: { value: 107, snapshot_max: 227, score: 47.1 },
      fragmentation: { value: 15, snapshot_max: 15, score: 100 },
      cluster_ambiguity: { value: 39.6, snapshot_max: 50, score: 79.2 },
    },
    priority_config: {
      weights: {
        publication_impact: 1 / 3,
        fragmentation: 1 / 3,
        cluster_ambiguity: 1 / 3,
      },
      max_top_candidate_share: 75,
    },
    target: {
      author_slug: "Eric_R_Larson",
      author_name: AUTHOR_NAME,
      author_affiliation: "Illinois Department of Natural Resources",
      openalex_id: "A5082046729",
    },
    affected_count: 107,
    version: 3,
    evidence: [
      {
        source: "openalex",
        source_refs: [{ entity_type: "author", id: "A5082046729" }],
        fetched_at: "2026-08-25T15:00:00Z",
        fetch_status: "success",
        field: "canonical_name",
        value: AUTHOR_NAME,
        value_state: "supports",
        interpretation: "The canonical name matches the dataset.",
      },
    ],
    detail: {
      candidate_ids: [
        {
          id: "39673101",
          share: 60.4,
          first_year: 2005,
          last_year: 2024,
          publications: [
            { year: 2024, title: "Environmental DNA surveillance" },
          ],
        },
      ],
      top_share: 60.4,
      openalex_topics: ["Environmental DNA"],
    },
    ...overrides,
  };
}

export function buildActivityEvent(
  overrides: Partial<ActivityEvent> = {},
): ActivityEvent {
  return {
    id: "event-one",
    case_id: CASE_ID,
    action_type: "flag_for_split",
    actor: REVIEWER.display_name,
    created_at: "2026-08-25T18:00:00Z",
    target_name: AUTHOR_NAME,
    note: "The publication clusters represent distinct researchers.",
    before: "pending",
    after: "needs_split",
    ...overrides,
  };
}

export function buildFetchRun(overrides: Partial<FetchRun> = {}): FetchRun {
  return {
    id: "fetch-one",
    status: "complete",
    current_source: null,
    source_progress: {},
    started_at: "2026-08-25T17:00:00Z",
    finished_at: "2026-08-25T17:05:00Z",
    last_completed_at: "2026-08-25T17:05:00Z",
    error: null,
    ...overrides,
  };
}

export function buildQueueSettings(
  overrides: Partial<QueueSettings> = {},
): QueueSettings {
  return {
    max_top_candidate_share: 75,
    weights: {
      publication_impact: 1,
      fragmentation: 1,
      cluster_ambiguity: 1,
    },
    version: 4,
    updated_at: "2026-08-25T17:00:00Z",
    ...overrides,
  };
}

export function buildOverview(
  overrides: Partial<ReviewOverview> = {},
): ReviewOverview {
  return {
    flagged_authors: 9,
    affected_publications: 968,
    total_authors: 50,
    total_publications: 5371,
    queue_updated_at: "2026-08-25T17:00:00Z",
    sources: [],
    ...overrides,
  };
}
