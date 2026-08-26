import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import type { EvidenceRecord } from "../../api/types";
import { buildReviewCase } from "../../test/data";
import Matrix from "./Matrix";

const FETCHED_AT = "2026-08-25T15:00:00Z";
const evidence: EvidenceRecord[] = [
  {
    source: "openalex",
    source_refs: [{ entity_type: "author", id: "A5082046729" }],
    fetched_at: FETCHED_AT,
    fetch_status: "success",
    field: "canonical_name",
    value: "Eric R. Larson",
    value_state: "supports",
    interpretation: "The names agree.",
  },
  {
    source: "orcid",
    source_refs: [{ entity_type: "author", id: "0000-0002-9232-5907" }],
    fetched_at: FETCHED_AT,
    fetch_status: "success",
    field: "affiliation",
    value: "University of Illinois Urbana-Champaign",
    value_state: "conflict",
    interpretation: "The current affiliations differ.",
  },
  {
    source: "orcid",
    source_refs: [{ entity_type: "author", id: "0000-0002-9232-5907" }],
    fetched_at: FETCHED_AT,
    fetch_status: "success",
    field: "profile_link",
    value: null,
    value_state: "missing",
    interpretation: "No profile link was returned.",
  },
  {
    source: "semantic_scholar",
    source_refs: [{ entity_type: "author", id: "39673101" }],
    fetched_at: FETCHED_AT,
    fetch_status: "success",
    field: "publications",
    value: "64 matched publications",
    value_state: "supports",
    interpretation: "The candidate contains matching publications.",
  },
  {
    source: "google_scholar",
    source_refs: [],
    fetched_at: FETCHED_AT,
    fetch_status: "rate_limited",
    field: "profile_link",
    value: null,
    value_state: "unverifiable",
    interpretation: "The request was rate limited.",
  },
];

function renderMatrix(
  onRefreshSource = vi.fn(),
  refreshing: "openalex" | null = null,
) {
  const reviewCase = buildReviewCase();
  const props = {
    evidence,
    target: reviewCase.target,
    importedAt: reviewCase.dataset_imported_at,
    refreshing,
    onRefreshSource,
    shares: { "39673101": 60.4 },
  } satisfies ComponentProps<typeof Matrix>;
  const view = render(<Matrix {...props} />);

  return {
    ...view,
    rerenderWith(overrides: Partial<ComponentProps<typeof Matrix>>) {
      view.rerender(<Matrix {...props} {...overrides} />);
    },
  };
}

it("renders representative values and distinguishes conflict, missing, and failed evidence", () => {
  renderMatrix();

  const table = screen.getByRole("table", {
    name: "Evidence by field and source",
  });
  expect(within(table).getByText("Dataset")).toBeInTheDocument();
  expect(
    within(table).getByText("64 matched publications"),
  ).toBeInTheDocument();
  expect(within(table).getByText("conflict")).toBeInTheDocument();
  expect(
    within(table).getByText("University of Illinois Urbana-Champaign"),
  ).toBeInTheDocument();
  expect(within(table).getByText("missing")).toBeInTheDocument();
  expect(within(table).getByText("429 rate limited")).toBeInTheDocument();
});

it("requests a source refresh and disables refresh actions while fetching", async () => {
  const user = userEvent.setup();
  const onRefreshSource = vi.fn();
  const { rerenderWith } = renderMatrix(onRefreshSource);

  await user.click(
    screen.getByRole("button", { name: "fetch OpenAlex evidence" }),
  );
  expect(onRefreshSource).toHaveBeenCalledWith("openalex");

  rerenderWith({ refreshing: "openalex" });
  expect(
    screen.getByRole("button", { name: "fetch OpenAlex evidence" }),
  ).toBeDisabled();
  expect(screen.getByText("fetching")).toBeInTheDocument();
});
