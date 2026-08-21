import casesJson from "../mock/cases.json";
import overviewJson from "../mock/overview.json";
import { matchesAuthorName } from "../lib/search";
import type {
  ActivityEvent,
  CasePriority,
  CaseQueryFilters,
  DecisionAction,
  ReviewStatus,
  DecisionRequest,
  ReviewOverview,
  ValidationCase,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_URL as string | undefined;
const MOCK_RESPONSE_DELAY_MS = 200;
const MOCK_REVIEWER = "aditya";

const PRIORITY_RANK: Record<CasePriority, number> = {
  high: 0,
  medium: 1,
  low: 2,
};

const mockCases = (casesJson as unknown as { cases: ValidationCase[] }).cases;

const MOCK_STORE_KEY = "mergereview.decisions";

interface MockStore {
  events: ActivityEvent[];
  decisions: Record<string, ReviewStatus>;
}

function readMockStore(): MockStore {
  try {
    const raw = window.localStorage.getItem(MOCK_STORE_KEY);
    if (!raw) return { events: [], decisions: {} };

    const parsed = JSON.parse(raw) as Partial<MockStore>;
    return {
      events: Array.isArray(parsed.events) ? parsed.events : [],
      decisions: parsed.decisions ?? {},
    };
  } catch {
    return { events: [], decisions: {} };
  }
}

function writeMockStore(store: MockStore) {
  try {
    window.localStorage.setItem(MOCK_STORE_KEY, JSON.stringify(store));
  } catch {
    // A full or blocked store leaves the session in memory only
  }
}

let mockStore = readMockStore();

function returnAfterMockDelay<T>(value: T): Promise<T> {
  return new Promise((resolve) => {
    setTimeout(() => resolve(value), MOCK_RESPONSE_DELAY_MS);
  });
}

async function getFromApiOrMock<T>(
  path: string,
  getMockValue: () => T,
): Promise<T> {
  if (!API_BASE_URL) {
    return returnAfterMockDelay(getMockValue());
  }

  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }

  return (await response.json()) as T;
}

function compareCases(a: ValidationCase, b: ValidationCase): number {
  const deferred =
    Number(a.status === "deferred") - Number(b.status === "deferred");
  if (deferred) return deferred;

  const priority = PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority];
  if (priority) return priority;

  const affected = b.affected_count - a.affected_count;
  if (affected) return affected;

  return a.id.localeCompare(b.id);
}

function applyMockStatus(reviewCase: ValidationCase): ValidationCase {
  const status = mockStore.decisions[reviewCase.id];
  return status ? { ...reviewCase, status } : reviewCase;
}

function caseMatchesFilters(
  reviewCase: ValidationCase,
  filters: CaseQueryFilters,
): boolean {
  if (filters.status) {
    const wanted = Array.isArray(filters.status)
      ? filters.status
      : [filters.status];
    if (!wanted.includes(reviewCase.status)) return false;
  }

  if (filters.priority && reviewCase.priority !== filters.priority)
    return false;

  if (
    filters.query &&
    !matchesAuthorName(reviewCase.target.author_name, filters.query)
  ) {
    return false;
  }

  return true;
}

function buildCaseQueryString(filters: CaseQueryFilters): string {
  const parameters = new URLSearchParams();

  for (const [name, value] of Object.entries(filters)) {
    if (Array.isArray(value)) {
      if (value.length) parameters.set(name, value.join(","));
    } else if (value) {
      parameters.set(name, value);
    }
  }

  return parameters.toString();
}

function getStatusAfterDecision(
  reviewCase: ValidationCase,
  action: DecisionAction,
): ReviewStatus {
  switch (action) {
    case "reopen":
      return "pending";
    case "confirm_one_author":
      return "one_author";
    case "flag_for_split":
      return "needs_split";
    case "mark_uncertain":
      return "uncertain";
    case "defer":
      return "deferred";
    case "note":
      return reviewCase.status;
  }
}

export function getOverview(): Promise<ReviewOverview> {
  return getFromApiOrMock(
    "/api/overview",
    () => overviewJson as ReviewOverview,
  );
}

export function listCases(
  filters: CaseQueryFilters = {},
): Promise<ValidationCase[]> {
  const queryString = buildCaseQueryString(filters);
  const path = `/api/cases${queryString ? `?${queryString}` : ""}`;

  return getFromApiOrMock(path, () =>
    mockCases
      .map(applyMockStatus)
      .filter((reviewCase) => caseMatchesFilters(reviewCase, filters))
      .sort(compareCases),
  );
}

export function getCase(caseId: string): Promise<ValidationCase> {
  return getFromApiOrMock(`/api/cases/${caseId}`, () => {
    const reviewCase = mockCases.find((candidate) => candidate.id === caseId);
    if (!reviewCase) throw new Error("404 Not Found");
    return applyMockStatus(reviewCase);
  });
}

export function listActivity(): Promise<ActivityEvent[]> {
  return getFromApiOrMock("/api/activity", () => [...mockStore.events]);
}

export async function postDecision(
  decision: DecisionRequest,
): Promise<ActivityEvent> {
  if (API_BASE_URL) {
    const response = await fetch(
      `${API_BASE_URL}/api/cases/${decision.case_id}/decisions`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action: decision.action,
          note: decision.note,
        }),
      },
    );

    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`);
    }

    return (await response.json()) as ActivityEvent;
  }

  const reviewCase = mockCases.find(
    (candidate) => candidate.id === decision.case_id,
  );
  if (!reviewCase) {
    throw new Error(`Unknown case: ${decision.case_id}`);
  }

  const currentCase = applyMockStatus(reviewCase);

  const nextStatus = getStatusAfterDecision(currentCase, decision.action);
  const activityEvent: ActivityEvent = {
    id: `e-${Date.now().toString(36)}`,
    case_id: reviewCase.id,
    action_type: decision.action,
    actor: MOCK_REVIEWER,
    created_at: new Date().toISOString(),
    target_name: reviewCase.target.author_name,
    note: decision.note?.trim() || null,
    before: currentCase.status,
    after: nextStatus,
  };

  mockStore = {
    events: [activityEvent, ...mockStore.events],
    decisions: {
      ...mockStore.decisions,
      [currentCase.id]: nextStatus,
    },
  };
  writeMockStore(mockStore);

  return returnAfterMockDelay(activityEvent);
}
