import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { getOverview, listActivity, listCases } from "../../api/client";
import {
  buildOverview,
  buildReviewCase,
  buildActivityEvent,
} from "../../test/data";
import { renderRoute } from "../../test/render";
import OverviewPage from "./OverviewPage";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  getOverview: vi.fn(),
  listActivity: vi.fn(),
  listCases: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(getOverview).mockResolvedValue(buildOverview());
  vi.mocked(listCases).mockResolvedValue([buildReviewCase()]);
  vi.mocked(listActivity).mockResolvedValue([]);
});

it("retains summary and pending cases when activity fails, retrying only activity", async () => {
  const user = userEvent.setup();
  vi.mocked(listActivity)
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValue([buildActivityEvent()]);
  renderRoute(<OverviewPage />, "/", "/");
  expect(
    await screen.findByText("Could not load recent activity"),
  ).toHaveAttribute("role", "alert");
  expect(
    screen.getByRole("link", { name: "Eric R. Larson" }),
  ).toBeInTheDocument();
  expect(screen.getByText("profiles assessed")).toBeInTheDocument();
  await user.click(
    screen.getByRole("button", { name: "retry recent activity" }),
  );
  expect(await screen.findByText("Test Reviewer")).toBeInTheDocument();
  expect(getOverview).toHaveBeenCalledOnce();
  expect(listCases).toHaveBeenCalledOnce();
  expect(listActivity).toHaveBeenCalledTimes(2);
});

it("keeps summary and activity when pending cases fail", async () => {
  vi.mocked(listCases).mockRejectedValue(new Error("offline"));
  vi.mocked(listActivity).mockResolvedValue([buildActivityEvent()]);
  renderRoute(<OverviewPage />, "/", "/");
  expect(
    await screen.findByText("Could not load pending cases"),
  ).toHaveAttribute("role", "alert");
  expect(await screen.findByText("Test Reviewer")).toBeInTheDocument();
  expect(screen.getByText("profiles assessed")).toBeInTheDocument();
});

it("does not wait for a stalled preview to display summary counts", async () => {
  vi.mocked(listActivity).mockReturnValue(new Promise(() => {}));
  renderRoute(<OverviewPage />, "/", "/");
  expect(await screen.findByText("50")).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "Eric R. Larson" }),
  ).toBeInTheDocument();
});
