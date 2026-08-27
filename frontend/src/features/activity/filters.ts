import type { ReviewStatus } from "../../api/types";
import type { SelectOption } from "../../components/Select";
import { statusText } from "../../lib/decisions";

export type TransitionFilter = ReviewStatus | "";
export const transitionOptions: SelectOption<TransitionFilter>[] = [
  { value: "", label: "any" },
  ...(
    ["pending", "one_author", "needs_split", "uncertain", "deferred"] as const
  ).map((value) => ({ value, label: statusText(value) })),
];

export type SinceFilter = "" | "1h" | "24h" | "7d" | "30d" | "run";
export const sinceOptions: SelectOption<SinceFilter>[] = [
  { value: "", label: "any time" },
  { value: "run", label: "since the last queue update" },
  { value: "1h", label: "last hour" },
  { value: "24h", label: "last 24 hours" },
  { value: "7d", label: "last 7 days" },
  { value: "30d", label: "last 30 days" },
];

export const SINCE_WINDOWS_MS = {
  "1h": 3_600_000,
  "24h": 86_400_000,
  "7d": 7 * 86_400_000,
  "30d": 30 * 86_400_000,
};

const SORT_COLUMNS = ["author", "reviewer", "time"] as const;
export type ActivitySort = (typeof SORT_COLUMNS)[number];

export function normalizeActivitySearch(
  params: URLSearchParams,
  reviewers?: string[],
): URLSearchParams {
  const normalized = new URLSearchParams(params);
  for (const name of ["from", "to"]) {
    if (!transitionOptions.some(({ value }) => value === params.get(name)))
      normalized.delete(name);
  }
  if (!sinceOptions.some(({ value }) => value === params.get("since")))
    normalized.delete("since");
  const reviewer = params.get("reviewer");
  if (reviewers && reviewer && !reviewers.includes(reviewer))
    normalized.delete("reviewer");
  const sort = SORT_COLUMNS.find((column) => column === params.get("sort"));
  if (!sort) normalized.delete("sort");
  if (!sort || params.get("dir") !== "asc") normalized.delete("dir");
  return normalized;
}

export function readActivityFilters(params: URLSearchParams) {
  const explicitSort =
    SORT_COLUMNS.find((column) => column === params.get("sort")) ?? null;
  return {
    fromStatus:
      transitionOptions.find(({ value }) => value === params.get("from"))
        ?.value ?? "",
    toStatus:
      transitionOptions.find(({ value }) => value === params.get("to"))
        ?.value ?? "",
    since:
      sinceOptions.find(({ value }) => value === params.get("since"))?.value ??
      "",
    reviewer: params.get("reviewer") ?? "",
    query: params.get("query") ?? "",
    noteQuery: params.get("note") ?? "",
    explicitSort,
    sort: explicitSort ?? "time",
    direction:
      explicitSort && params.get("dir") === "asc"
        ? ("asc" as const)
        : ("desc" as const),
  };
}
