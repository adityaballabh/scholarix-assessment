import type { SelectOption } from "../../components/Select";
import type {
  CasePriority,
  CaseQueryFilters,
  ReviewStatus,
} from "../../api/types";

export type StatusFilter = ReviewStatus | "all";
export type PriorityFilter = CasePriority | "";

export const priorityOptions: SelectOption<PriorityFilter>[] = [
  { value: "", label: "all priorities" },
  { value: "high", label: "high" },
  { value: "medium", label: "medium" },
  { value: "low", label: "low" },
];

export const statusOptions: SelectOption<StatusFilter>[] = [
  { value: "all", label: "all states" },
  { value: "pending", label: "pending" },
  { value: "in_review", label: "in review" },
  { value: "deferred", label: "deferred" },
  { value: "reopened", label: "reopened" },
  { value: "resolved", label: "resolved" },
];

export const DEFAULT_STATUS: StatusFilter = "pending";

export function readOption<T extends string>(
  raw: string | null,
  options: SelectOption<T>[],
  fallback: T,
): T {
  return options.some((option) => option.value === raw) ? (raw as T) : fallback;
}

export function getStatusFilter(status: StatusFilter): CaseQueryFilters["status"] {
  return status === "all" ? undefined : status;
}

export function readCaseFilters(searchParams: URLSearchParams): CaseQueryFilters {
  const query = searchParams.get("query") ?? "";
  const priority = readOption(searchParams.get("priority"), priorityOptions, "");
  const status = readOption(searchParams.get("status"), statusOptions, DEFAULT_STATUS);

  return {
    query: query || undefined,
    priority: priority || undefined,
    status: getStatusFilter(status),
  };
}
