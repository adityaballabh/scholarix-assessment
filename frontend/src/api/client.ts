import type {
  ActivityEvent,
  AuditConfig,
  AuditConfigUpdate,
  AuditResult,
  AuditRun,
  CaseQueryFilters,
  DecisionRequest,
  RefreshResult,
  RefreshSource,
  ReviewOverview,
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

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
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

export function getAudit(): Promise<AuditRun | null> {
  return requestJson("/api/fetches/current");
}

export function startAudit(): Promise<AuditRun> {
  return requestJson("/api/fetches", { method: "POST" });
}

export function abandonAudit(auditId: string): Promise<AuditRun> {
  return requestJson(`/api/fetches/${auditId}/abandon`, { method: "POST" });
}

export function getAuditConfig(): Promise<AuditConfig> {
  return requestJson("/api/audit-config");
}

export function updateAuditConfig(
  config: AuditConfigUpdate,
): Promise<AuditConfig> {
  return requestJson("/api/audit-config", {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(config),
  });
}

export function runAudit(): Promise<AuditResult> {
  return requestJson("/api/audits", { method: "POST" });
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
