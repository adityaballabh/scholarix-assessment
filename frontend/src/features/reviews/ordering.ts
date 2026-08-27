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
    const difference = sortValue(left) - sortValue(right);
    if (difference) return direction === "asc" ? difference : -difference;
    return (
      right.priority_score - left.priority_score ||
      (right.detail.top_share ?? 0) - (left.detail.top_share ?? 0) ||
      right.detail.candidate_ids.length - left.detail.candidate_ids.length ||
      right.affected_count - left.affected_count ||
      statusOrder.indexOf(left.status) - statusOrder.indexOf(right.status) ||
      (left.id < right.id ? -1 : left.id > right.id ? 1 : 0)
    );
  });
}
