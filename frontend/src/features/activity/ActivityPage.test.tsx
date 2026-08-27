import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { getOverview, listActivity } from "../../api/client";
import { buildActivityEvent, buildOverview } from "../../test/data";
import { renderRoute } from "../../test/render";
import ActivityPage from "./ActivityPage";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  getOverview: vi.fn(),
  listActivity: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(getOverview).mockResolvedValue(buildOverview());
  vi.mocked(listActivity).mockResolvedValue([
    buildActivityEvent(),
    buildActivityEvent({
      id: "event-two",
      case_id: "case-boxuan-zhao",
      target_name: "Boxuan Zhao",
      actor: "Second Reviewer",
      note: "The evidence supports one researcher.",
      action_type: "confirm_one_author",
      after: "one_author",
      created_at: "2026-08-25T17:00:00Z",
    }),
  ]);
});

it("combines author and note filters in the URL", async () => {
  const user = userEvent.setup();
  renderRoute(<ActivityPage />, "/activity", "/activity");
  await screen.findByRole("table", { name: "Recorded decisions" });

  await user.type(
    screen.getByRole("searchbox", { name: "search author" }),
    "Eric",
  );
  await user.type(
    screen.getByRole("searchbox", { name: "search notes" }),
    "clusters",
  );

  expect(screen.getByText("Eric R. Larson")).toBeInTheDocument();
  expect(screen.queryByText("Boxuan Zhao")).not.toBeInTheDocument();
  expect(screen.getByTestId("location")).toHaveTextContent("query=Eric");
  expect(screen.getByTestId("location")).toHaveTextContent("note=clusters");
});

it("explains when the last queue update filter is unavailable", async () => {
  vi.mocked(getOverview).mockRejectedValue(new Error("unavailable"));
  renderRoute(<ActivityPage />, "/activity?since=run", "/activity");

  expect(
    await screen.findByText("Could not load the last queue update time"),
  ).toHaveAttribute("role", "alert");
});

it("shows an activity load error", async () => {
  vi.mocked(listActivity).mockRejectedValue(new Error("unavailable"));
  renderRoute(<ActivityPage />, "/activity", "/activity");

  expect(await screen.findByText("Could not load activity")).toHaveAttribute(
    "role",
    "alert",
  );
});

it("removes an unknown reviewer without applying an invisible filter", async () => {
  renderRoute(<ActivityPage />, "/activity?reviewer=Ghost", "/activity");
  await screen.findByRole("table", { name: "Recorded decisions" });
  expect(screen.getByText("Eric R. Larson")).toBeInTheDocument();
  expect(screen.getByText("Boxuan Zhao")).toBeInTheDocument();
  await waitFor(() =>
    expect(screen.getByTestId("location").textContent).toBe("/activity"),
  );
  expect(
    screen.getByRole("button", { name: "reviewer: all reviewers" }),
  ).toBeInTheDocument();
});

it("ignores orphan direction and announces effective default sorting", async () => {
  const user = userEvent.setup();
  renderRoute(<ActivityPage />, "/activity?dir=asc", "/activity");
  await screen.findByRole("table", { name: "Recorded decisions" });
  await waitFor(() =>
    expect(screen.getByTestId("location").textContent).toBe("/activity"),
  );
  const timeHeader = screen
    .getByRole("button", { name: "Sort by time, ascending" })
    .closest('[role="columnheader"]');
  expect(timeHeader).toHaveAttribute("aria-sort", "descending");
  await user.click(
    screen.getByRole("button", { name: "Sort by time, ascending" }),
  );
  expect(screen.getByTestId("location")).toHaveTextContent("sort=time&dir=asc");
  expect(timeHeader).toHaveAttribute("aria-sort", "ascending");
});
