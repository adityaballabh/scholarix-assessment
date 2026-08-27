import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { listCases } from "../../api/client";
import type { CaseQueryFilters } from "../../api/types";
import { AUTHOR_NAME, SECOND_CASE_ID, buildReviewCase } from "../../test/data";
import { renderRoute } from "../../test/render";
import QueuePage from "./QueuePage";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  listCases: vi.fn(),
}));

it("preserves the status filter when debounced search updates the URL", async () => {
  const user = userEvent.setup();
  vi.mocked(listCases).mockResolvedValue([buildReviewCase()]);
  renderRoute(<QueuePage />, "/reviews?status=deferred", "/reviews");

  await screen.findByRole("rowheader", { name: AUTHOR_NAME });
  await user.type(
    screen.getByRole("searchbox", { name: "Search reviews" }),
    "Eric",
  );

  await waitFor(() => {
    expect(screen.getByTestId("location")).toHaveTextContent("status=deferred");
    expect(screen.getByTestId("location")).toHaveTextContent("query=Eric");
  });
  expect(listCases).toHaveBeenLastCalledWith({
    query: "Eric",
    scope: "active",
    status: "deferred",
  });
  expect(screen.getByRole("link", { name: "export evidence" })).toHaveAttribute(
    "href",
    "/api/export?query=Eric&scope=active&status=deferred",
  );
});

it("distinguishes an empty filter result from an empty queue", async () => {
  const reviewCase = buildReviewCase();
  vi.mocked(listCases).mockImplementation((filters: CaseQueryFilters = {}) =>
    Promise.resolve(filters.status ? [] : [reviewCase]),
  );
  renderRoute(<QueuePage />, "/reviews", "/reviews");

  expect(
    await screen.findByText("No reviews match the current filters"),
  ).toBeInTheDocument();
  expect(screen.queryByText("No reviews left")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: "export evidence" }),
  ).not.toBeInTheDocument();
});

it("shows a queue load error", async () => {
  vi.mocked(listCases).mockImplementation((filters: CaseQueryFilters = {}) =>
    filters.status
      ? Promise.reject(new Error("unavailable"))
      : Promise.resolve([buildReviewCase()]),
  );
  renderRoute(<QueuePage />, "/reviews", "/reviews");

  expect(
    await screen.findByText("Could not load the review queue"),
  ).toHaveAttribute("role", "alert");
});

it("sorts visible rows without dropping the current filter", async () => {
  const user = userEvent.setup();
  const lowerPriority = buildReviewCase({
    id: SECOND_CASE_ID,
    priority_score: 40,
    target: {
      author_slug: "Boxuan_Zhao",
      author_name: "Boxuan Zhao",
      author_affiliation: "University of Illinois Urbana-Champaign",
      openalex_id: "A123",
    },
  });
  vi.mocked(listCases).mockResolvedValue([lowerPriority, buildReviewCase()]);
  renderRoute(<QueuePage />, "/reviews?status=all", "/reviews");
  await screen.findByRole("rowheader", { name: AUTHOR_NAME });

  await user.click(
    screen.getByRole("button", { name: "Sort by score, descending" }),
  );

  expect(
    screen.getAllByRole("rowheader").map((row) => row.textContent),
  ).toEqual([AUTHOR_NAME, "Boxuan Zhao"]);
  expect(screen.getByTestId("location")).toHaveTextContent("status=all");
  expect(screen.getByTestId("location")).toHaveTextContent("sort=score");
});
