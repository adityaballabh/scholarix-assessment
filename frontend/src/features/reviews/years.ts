import type { SemanticScholarCandidate } from "../../api/types";

export function yearSpan(candidate: SemanticScholarCandidate): string | null {
  const { first_year, last_year } = candidate;
  if (first_year === null || last_year === null) return null;
  return first_year === last_year
    ? `${first_year}`
    : `${first_year}–${last_year}`;
}

export function leadTitle(candidate: SemanticScholarCandidate): string {
  return candidate.publications[0]?.title ?? "—";
}
