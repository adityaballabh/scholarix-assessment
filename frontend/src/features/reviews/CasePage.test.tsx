import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  ApiError,
  getCase,
  listActivity,
  listCases,
  postDecision,
  refreshAuthorEvidence,
  refreshAuthorSource,
} from "../../api/client";
import type { RefreshResult } from "../../api/types";
import {
  CASE_ID,
  SECOND_CASE_ID,
  buildActivityEvent,
  buildReviewCase,
} from "../../test/data";
import { renderRoute } from "../../test/render";
import CasePage from "./CasePage";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  getCase: vi.fn(),
  listActivity: vi.fn(),
  listCases: vi.fn(),
  postDecision: vi.fn(),
  refreshAuthorEvidence: vi.fn(),
  refreshAuthorSource: vi.fn(),
}));

const REFRESH_RESULT: RefreshResult = {
  scope: "author",
  target: "Eric_R_Larson",
  results: { success: 1 },
  cases: 9,
};

beforeEach(() => {
  const reviewCase = buildReviewCase();
  const secondCase = buildReviewCase({
    id: SECOND_CASE_ID,
    target: {
      author_slug: "Boxuan_Zhao",
      author_name: "Boxuan Zhao",
      author_affiliation: "University of Illinois Urbana-Champaign",
      openalex_id: "A123",
    },
  });
  vi.mocked(getCase).mockImplementation((caseId) =>
    Promise.resolve(caseId === SECOND_CASE_ID ? secondCase : reviewCase),
  );
  vi.mocked(listCases).mockResolvedValue([reviewCase, secondCase]);
  vi.mocked(listActivity).mockResolvedValue([]);
});

function renderCase() {
  return renderRoute(
    <CasePage />,
    `/reviews/${CASE_ID}?status=pending`,
    "/reviews/:caseId",
  );
}

it("records a decision and advances to the next queue case", async () => {
  const user = userEvent.setup();
  const event = buildActivityEvent();
  vi.mocked(postDecision).mockResolvedValue(event);
  renderCase();
  await screen.findByRole("heading", { name: "Eric R. Larson" });

  await user.click(screen.getByRole("button", { name: "needs split" }));
  const dialog = screen.getByRole("dialog", { name: "needs split" });
  await user.type(
    within(dialog).getByPlaceholderText("optional note"),
    "Publication clusters represent different researchers.",
  );
  await user.click(within(dialog).getByRole("button", { name: "needs split" }));

  expect(postDecision).toHaveBeenCalledWith({
    case_id: CASE_ID,
    action: "flag_for_split",
    note: "Publication clusters represent different researchers.",
    expected_version: 3,
  });
  await waitFor(() =>
    expect(screen.getByTestId("location")).toHaveTextContent(
      `/reviews/${SECOND_CASE_ID}?status=pending`,
    ),
  );
});

it("keeps the decision dialog open after a version conflict", async () => {
  const user = userEvent.setup();
  vi.mocked(postDecision).mockRejectedValue(new ApiError(409, "Case changed"));
  renderCase();
  await screen.findByRole("heading", { name: "Eric R. Larson" });

  await user.click(screen.getByRole("button", { name: "one author" }));
  const dialog = screen.getByRole("dialog", { name: "one author" });
  await user.click(within(dialog).getByRole("button", { name: "one author" }));

  expect(
    await within(dialog).findByText(
      "The decision was not recorded. Reload the case and try again.",
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByText("case changed, reload and try again"),
  ).toBeInTheDocument();
  expect(screen.getByTestId("location")).toHaveTextContent(
    `/reviews/${CASE_ID}`,
  );
});

it("reloads the case after fetching all evidence", async () => {
  const user = userEvent.setup();
  vi.mocked(refreshAuthorEvidence).mockResolvedValue(REFRESH_RESULT);
  renderCase();
  await screen.findByRole("heading", { name: "Eric R. Larson" });

  await user.click(screen.getByRole("button", { name: "fetch all evidence" }));

  expect(refreshAuthorEvidence).toHaveBeenCalledWith("Eric_R_Larson");
  expect(await screen.findByText("All evidence fetched.")).toBeInTheDocument();
  expect(getCase).toHaveBeenCalledTimes(2);
});

it("reports a source-specific evidence refresh failure", async () => {
  const user = userEvent.setup();
  vi.mocked(refreshAuthorSource).mockRejectedValue(new Error("unavailable"));
  renderCase();
  await screen.findByRole("heading", { name: "Eric R. Larson" });

  await user.click(
    screen.getByRole("button", { name: "fetch OpenAlex evidence" }),
  );

  expect(refreshAuthorSource).toHaveBeenCalledWith("Eric_R_Larson", "openalex");
  expect(
    await screen.findByText("OpenAlex evidence could not be fetched."),
  ).toHaveAttribute("role", "alert");
});
