import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  ApiError,
  getQueueSettings,
  rebuildQueue,
  updateQueueSettings,
} from "../../api/client";
import { buildQueueSettings } from "../../test/data";
import { renderRoute } from "../../test/render";
import ScoreSettingsPage from "./ScoreSettingsPage";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  getQueueSettings: vi.fn(),
  rebuildQueue: vi.fn(),
  updateQueueSettings: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(getQueueSettings).mockResolvedValue(buildQueueSettings());
});

function renderSettings() {
  return renderRoute(
    <ScoreSettingsPage />,
    "/reviews/settings",
    "/reviews/settings",
  );
}

it("saves valid changes before rebuilding the queue", async () => {
  const user = userEvent.setup();
  vi.mocked(updateQueueSettings).mockResolvedValue(
    buildQueueSettings({ max_top_candidate_share: 70, version: 5 }),
  );
  vi.mocked(rebuildQueue).mockResolvedValue({ config_version: 5, cases: 8 });
  renderSettings();

  const limit = await screen.findByLabelText("top share limit");
  await user.clear(limit);
  await user.type(limit, "70");
  await user.click(
    screen.getByRole("button", { name: "save and rebuild queue" }),
  );

  expect(updateQueueSettings).toHaveBeenCalledWith({
    max_top_candidate_share: 70,
    weights: {
      publication_impact: 1,
      fragmentation: 1,
      cluster_ambiguity: 1,
    },
    expected_version: 4,
  });
  expect(rebuildQueue).toHaveBeenCalledOnce();
  expect(
    vi.mocked(updateQueueSettings).mock.invocationCallOrder[0],
  ).toBeLessThan(vi.mocked(rebuildQueue).mock.invocationCallOrder[0]);
  await waitFor(() =>
    expect(screen.getByTestId("location")).toHaveTextContent("/reviews"),
  );
});

it("blocks invalid eligibility settings", async () => {
  const user = userEvent.setup();
  renderSettings();

  const limit = await screen.findByLabelText("top share limit");
  await user.clear(limit);
  await user.type(limit, "101");

  expect(
    screen.getByText("Top share limit must be between 0 and 100"),
  ).toHaveAttribute("role", "alert");
  expect(
    screen.getByRole("button", { name: "save and rebuild queue" }),
  ).toBeDisabled();
  expect(updateQueueSettings).not.toHaveBeenCalled();
});

it("reports a settings version conflict without rebuilding", async () => {
  const user = userEvent.setup();
  vi.mocked(updateQueueSettings).mockRejectedValue(
    new ApiError(409, "Settings changed"),
  );
  renderSettings();

  const limit = await screen.findByLabelText("top share limit");
  await user.clear(limit);
  await user.type(limit, "70");
  await user.click(
    screen.getByRole("button", { name: "save and rebuild queue" }),
  );

  expect(
    await screen.findByText(
      "Queue settings changed elsewhere — reload and try again",
    ),
  ).toHaveAttribute("role", "alert");
  expect(rebuildQueue).not.toHaveBeenCalled();
});
