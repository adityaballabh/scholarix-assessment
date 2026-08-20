import type { DecisionAction } from "../api/types";

export const actionLabels: Record<DecisionAction, string> = {
  reopen: "returned to pending",
  confirm_one_author: "one author",
  flag_for_split: "needs split",
  mark_uncertain: "uncertain",
  defer: "deferred",
  note: "note added",
};

export function statusText(status: string | null) {
  return status ? status.replace(/_/g, " ") : "—";
}
