import type {
  ActivityEvent,
  QueueSettings,
  QueueSettingsUpdate,
  QueueRebuildResult,
  FetchRun,
  CaseQueryFilters,
  DecisionRequest,
  RefreshResult,
  RefreshSource,
  Credentials,
  Registration,
  ReviewOverview,
  User,
  ValidationCase,
} from "./types";

const API_BASE_URL =
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ??
  "";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/**
 * Reads are public and writes are not, so a 401 means the reviewer needs to sign
 * in before this exact call can proceed. The handler resolves true once they have.
 */
let onUnauthorized: (() => Promise<boolean>) | null = null;

export function setUnauthorizedHandler(
  handler: (() => Promise<boolean>) | null,
): void {
  onUnauthorized = handler;
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${API_BASE_URL}${path}`, { ...init, credentials: "include" });
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response = await send(path, init);
  if (
    response.status === 401 &&
    onUnauthorized &&
    !path.startsWith("/api/auth")
  ) {
    if (await onUnauthorized()) response = await send(path, init);
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {}
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
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

export function getOverview(): Promise<ReviewOverview> {
  return requestJson("/api/overview");
}

export function listCases(
  filters: CaseQueryFilters = {},
): Promise<ValidationCase[]> {
  const queryString = buildCaseQueryString(filters);
  return requestJson(`/api/cases${queryString ? `?${queryString}` : ""}`);
}

/**
 * Export is a file download, not JSON for the app to render, so these build URLs for a
 * plain anchor instead of going through requestJson. Both endpoints are GETs, and reads
 * are open, so no session handling is involved.
 */
export function caseExportUrl(caseId: string): string {
  return `${API_BASE_URL}/api/cases/${encodeURIComponent(caseId)}/export`;
}

export function queueExportUrl(filters: CaseQueryFilters = {}): string {
  const queryString = buildCaseQueryString(filters);
  return `${API_BASE_URL}/api/export${queryString ? `?${queryString}` : ""}`;
}

export function getCase(caseId: string): Promise<ValidationCase> {
  return requestJson(`/api/cases/${caseId}`);
}

export function listActivity(): Promise<ActivityEvent[]> {
  return requestJson("/api/activity");
}

export function postDecision(
  decision: DecisionRequest,
): Promise<ActivityEvent> {
  return requestJson(`/api/cases/${decision.case_id}/decisions`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      action: decision.action,
      note: decision.note,
      expected_version: decision.expected_version,
    }),
  });
}

export function getFetch(): Promise<FetchRun | null> {
  return requestJson("/api/fetches/current");
}

export function startFetch(): Promise<FetchRun> {
  return requestJson("/api/fetches", { method: "POST" });
}

export function abandonFetch(fetchId: string): Promise<FetchRun> {
  return requestJson(`/api/fetches/${fetchId}/abandon`, { method: "POST" });
}

export function getQueueSettings(): Promise<QueueSettings> {
  return requestJson("/api/queue/settings");
}

export function updateQueueSettings(
  config: QueueSettingsUpdate,
): Promise<QueueSettings> {
  return requestJson("/api/queue/settings", {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(config),
  });
}

export function rebuildQueue(): Promise<QueueRebuildResult> {
  return requestJson("/api/queue/rebuild", { method: "POST" });
}

export function refreshAuthorEvidence(
  authorSlug: string,
): Promise<RefreshResult> {
  return requestJson(`/api/refresh/authors/${encodeURIComponent(authorSlug)}`, {
    method: "POST",
  });
}

export function refreshAuthorSource(
  authorSlug: string,
  source: RefreshSource,
): Promise<RefreshResult> {
  return requestJson(
    `/api/refresh/authors/${encodeURIComponent(authorSlug)}/sources/${source}`,
    { method: "POST" },
  );
}

export function getCurrentUser(): Promise<User> {
  return requestJson("/api/auth/me");
}

export function signIn(credentials: Credentials): Promise<User> {
  return requestJson("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(credentials),
  });
}

export function createAccount(registration: Registration): Promise<User> {
  return requestJson("/api/auth/register", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(registration),
  });
}

export async function signOut(): Promise<void> {
  await send("/api/auth/logout", { method: "POST" });
}
