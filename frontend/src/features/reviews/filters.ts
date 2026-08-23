import type { SelectOption } from "../../components/Select";
import type {
  CaseQueryFilters,
  QueueScope,
  ReviewStatus,
} from "../../api/types";

export type StatusFilter = ReviewStatus | "all";

export const statusOptions: SelectOption<StatusFilter>[] = [
  { value: "all", label: "all states" },
  { value: "pending", label: "pending" },
  { value: "one_author", label: "one author" },
  { value: "needs_split", label: "needs split" },
  { value: "uncertain", label: "uncertain" },
  { value: "deferred", label: "deferred" },
];

export const DEFAULT_STATUS: StatusFilter = "pending";

export function readQueueScope(raw: string | null): QueueScope {
  return raw === "archived" ? "archived" : "active";
}

export function defaultStatusForScope(scope: QueueScope): StatusFilter {
  return scope === "archived" ? "all" : DEFAULT_STATUS;
}

export function readOption<T extends string>(
  raw: string | null,
  options: SelectOption<T>[],
  fallback: T,
): T {
  return options.some((option) => option.value === raw) ? (raw as T) : fallback;
}

export function getStatusFilter(
  status: StatusFilter,
): CaseQueryFilters["status"] {
  return status === "all" ? undefined : status;
}

export function readCaseFilters(
  searchParams: URLSearchParams,
): CaseQueryFilters {
  const scope = readQueueScope(searchParams.get("scope"));
  const query = searchParams.get("query") ?? "";
  const status = readOption(
    searchParams.get("status"),
    statusOptions,
    defaultStatusForScope(scope),
  );

  return {
    query: query || undefined,
    scope,
    status: getStatusFilter(status),
  };
}

export const statusOrder: ReviewStatus[] = statusOptions
  .map((option) => option.value)
  .filter((value): value is ReviewStatus => value !== "all");
