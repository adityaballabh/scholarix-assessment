import casesJson from "../mock/cases.json";
import overviewJson from "../mock/overview.json";
import type {
  ActivityEvent,
  CaseQueryFilters,
  DecisionAction,
  DecisionRequest,
  ReviewOverview,
  ValidationCase,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_URL as string | undefined;
const MOCK_RESPONSE_DELAY_MS = 200;
const MOCK_REVIEWER = "aditya";

const mockCases = (casesJson as unknown as { cases: ValidationCase[] }).cases;
const mockActivityEvents: ActivityEvent[] = [];
const mockCaseStatuses = new Map<string, ValidationCase["status"]>();

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

function applyMockStatus(reviewCase: ValidationCase): ValidationCase {
  const currentStatus = mockCaseStatuses.get(reviewCase.id);
  return currentStatus ? { ...reviewCase, status: currentStatus } : reviewCase;
}

function caseMatchesFilters(
  reviewCase: ValidationCase,
  filters: CaseQueryFilters,
): boolean {
  if (filters.status && reviewCase.status !== filters.status) return false;
  if (filters.priority && reviewCase.priority !== filters.priority) return false;

  if (filters.query) {
    const query = filters.query.toLowerCase();
    const searchableText = [
      reviewCase.target.author_name,
      reviewCase.summary,
    ]
      .join(" ")
      .toLowerCase();

    if (!searchableText.includes(query)) return false;
  }

  return true;
}

function buildCaseQueryString(filters: CaseQueryFilters): string {
  const parameters = new URLSearchParams();

  for (const [name, value] of Object.entries(filters)) {
    if (value) parameters.set(name, value);
  }

  return parameters.toString();
}

function getStatusAfterDecision(
  reviewCase: ValidationCase,
  action: DecisionAction,
): ValidationCase["status"] {
  switch (action) {
    case "defer":
      return "deferred";
    case "note":
      return reviewCase.status;
    case "accept_merge":
    case "keep_separate":
    case "mark_uncertain":
      return "resolved";
  }
}

export function getOverview(): Promise<ReviewOverview> {
  return getFromApiOrMock("/api/overview", () => overviewJson as ReviewOverview);
}

export function listCases(
  filters: CaseQueryFilters = {},
): Promise<ValidationCase[]> {
  const queryString = buildCaseQueryString(filters);
  const path = `/api/cases${queryString ? `?${queryString}` : ""}`;

  return getFromApiOrMock(path, () =>
    mockCases.map(applyMockStatus).filter((reviewCase) =>
      caseMatchesFilters(reviewCase, filters),
    ),
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
  return getFromApiOrMock("/api/activity", () => [...mockActivityEvents]);
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
          resolved: decision.resolved,
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
  mockCaseStatuses.set(
    currentCase.id,
    getStatusAfterDecision(currentCase, decision.action),
  );

  const resolvedFields = Object.entries(decision.resolved ?? {});
  const activityEvent: ActivityEvent = {
    id: `e-${Date.now().toString(36)}`,
    case_id: reviewCase.id,
    action_type: decision.action,
    actor: MOCK_REVIEWER,
    created_at: new Date().toISOString(),
    target_name: reviewCase.target.author_name,
    note: decision.note?.trim() || null,
    before: resolvedFields[0]?.[0] ?? null,
    after: resolvedFields[0]?.[1] ?? null,
    supersedes_event_id: null,
  };

  mockActivityEvents.unshift(activityEvent);
  return returnAfterMockDelay(activityEvent);
}

export const usingMockData = !API_BASE_URL;
