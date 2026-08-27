import type { ValidationCase } from "../../api/types";
import type { SortDirection } from "../../components/SortHeader";
import { statusOrder } from "./filters";

const SORT_COLUMNS = [
  "score",
  "share",
  "candidates",
  "publications",
  "status",
] as const;
export type QueueSortColumn = (typeof SORT_COLUMNS)[number];

export function readQueueSort(params: URLSearchParams): {
  column: QueueSortColumn | null;
  direction: SortDirection;
} {
  const column =
    SORT_COLUMNS.find((value) => value === params.get("sort")) ?? null;
  return {
    column,
    direction: column && params.get("dir") === "asc" ? "asc" : "desc",
  };
}

export function orderCases(
  cases: ValidationCase[],
  column: QueueSortColumn | null,
  direction: SortDirection,
): ValidationCase[] {
  function sortValue(reviewCase: ValidationCase): number {
    switch (column) {
      case "score":
        return reviewCase.priority_score;
      case "share":
        return reviewCase.detail.top_share ?? 0;
      case "candidates":
        return reviewCase.detail.candidate_ids.length;
      case "publications":
        return reviewCase.affected_count;
      case "status":
        return statusOrder.indexOf(reviewCase.status);
      default:
        return 0;
    }
  }

  return [...cases].sort((left, right) => {
    const deferredOrder =
      Number(left.status === "deferred") - Number(right.status === "deferred");
    if (deferredOrder) return deferredOrder;
    const difference = sortValue(left) - sortValue(right);
    return direction === "asc" ? difference : -difference;
  });
}
