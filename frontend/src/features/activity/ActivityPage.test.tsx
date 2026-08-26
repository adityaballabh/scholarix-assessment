import { screen } from "@testing-library/react";
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
    await screen.findByText("The last queue update time could not be loaded."),
  ).toHaveAttribute("role", "alert");
});

it("shows an activity load error", async () => {
  vi.mocked(listActivity).mockRejectedValue(new Error("unavailable"));
  renderRoute(<ActivityPage />, "/activity", "/activity");

  expect(
    await screen.findByText("Activity could not be loaded."),
  ).toHaveAttribute("role", "alert");
});
