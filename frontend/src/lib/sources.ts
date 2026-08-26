const SOURCE_LABELS: Record<string, string> = {
  openalex: "OpenAlex",
  openalex_authors: "OpenAlex authors",
  openalex_author_publications: "OpenAlex author publications",
  openalex_publications: "OpenAlex publications",
  orcid: "ORCID",
  semantic_scholar: "Semantic Scholar",
  google_scholar: "Google Scholar",
  pubmed: "PubMed",
  case_generation: "Case generation",
};

export const FETCH_SOURCE_ORDER = [
  "openalex_authors",
  "openalex_author_publications",
  "openalex_publications",
  "orcid",
  "semantic_scholar",
  "case_generation",
];

export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source.replace(/_/g, " ");
}
