import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError, getCase } from "../../api/client";
import { buildReviewCase, CASE_ID } from "../../test/data";
import { renderRoute } from "../../test/render";
import ClustersPage from "./ClustersPage";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  getCase: vi.fn(),
}));

it("reserves the missing-case message for a 404", async () => {
  vi.mocked(getCase).mockRejectedValue(new ApiError(404, "Case not found"));
  renderRoute(
    <ClustersPage />,
    `/reviews/${CASE_ID}/ids`,
    "/reviews/:caseId/ids",
  );
  expect(
    await screen.findByText(`Case not found: ${CASE_ID}`, { exact: false }),
  ).toBeInTheDocument();
  expect(screen.queryByText("Could not load the case")).not.toBeInTheDocument();
});

it.each([new ApiError(500, "Server error"), new Error("offline")])(
  "keeps retrieval failures separate and supports retry",
  async (error) => {
    const user = userEvent.setup();
    vi.mocked(getCase)
      .mockRejectedValueOnce(error)
      .mockResolvedValue(buildReviewCase());
    renderRoute(
      <ClustersPage />,
      `/reviews/${CASE_ID}/ids`,
      "/reviews/:caseId/ids",
    );
    expect(await screen.findByText("Could not load the case")).toHaveAttribute(
      "role",
      "alert",
    );
    expect(screen.queryByText(/Case not found:/)).toBeNull();
    await user.click(screen.getByRole("button", { name: "retry" }));
    expect(
      await screen.findByRole("heading", { name: "Eric R. Larson" }),
    ).toBeInTheDocument();
  },
);
