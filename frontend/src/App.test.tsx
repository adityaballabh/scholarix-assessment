import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ApiError, abandonFetch, getFetch, startFetch } from "./api/client";
import { buildFetchRun } from "./test/data";
import App from "./App";

vi.mock("./api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api/client")>()),
  abandonFetch: vi.fn(),
  getFetch: vi.fn(),
  startFetch: vi.fn(),
}));

vi.mock("./features/auth/AuthProvider", () => ({
  useSession: () => ({
    user: null,
    ready: true,
    signOut: vi.fn(),
  }),
}));

vi.mock("./features/overview/OverviewPage", () => ({
  default: () => <h1>Overview content</h1>,
}));

function renderApp() {
  return render(
    <MemoryRouter
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <App />
    </MemoryRouter>,
  );
}

it("starts the initial fetch from its confirmation", async () => {
  const user = userEvent.setup();
  vi.mocked(getFetch).mockResolvedValue(null);
  vi.mocked(startFetch).mockResolvedValue(
    buildFetchRun({
      status: "queued",
      current_source: "openalex_authors",
      source_progress: {
        openalex_authors: { completed: 0, total: 50, by_status: {} },
      },
      last_completed_at: null,
    }),
  );
  renderApp();

  expect(
    await screen.findByRole("heading", { name: "Initial fetch pending" }),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "fetch data" }));
  const dialog = screen.getByRole("dialog", { name: "Fetch data" });
  await user.click(within(dialog).getByRole("button", { name: "fetch data" }));

  expect(startFetch).toHaveBeenCalledOnce();
  expect(
    await screen.findByRole("heading", { name: "Fetch in progress" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("progressbar")).toHaveAttribute("value", "0");
  expect(screen.getByRole("progressbar")).toHaveAttribute("max", "50");
});

it.each([
  [423, "A fetch is already running"],
  [404, "No dataset to fetch"],
  [500, "The fetch could not be started"],
])("explains a %s fetch start failure", async (status, message) => {
  const user = userEvent.setup();
  vi.mocked(getFetch).mockResolvedValue(null);
  vi.mocked(startFetch).mockRejectedValue(new ApiError(status, "failure"));
  renderApp();

  await screen.findByRole("heading", { name: "Initial fetch pending" });
  await user.click(screen.getByRole("button", { name: "fetch data" }));
  const dialog = screen.getByRole("dialog", { name: "Fetch data" });
  await user.click(within(dialog).getByRole("button", { name: "fetch data" }));

  expect(await within(dialog).findByText(message)).toHaveAttribute(
    "role",
    "alert",
  );
});

it("shows running progress instead of the application shell", async () => {
  vi.mocked(getFetch).mockResolvedValue(
    buildFetchRun({
      status: "running",
      current_source: "semantic_scholar",
      source_progress: {
        semantic_scholar: {
          completed: 24,
          total: 50,
          by_status: { success: 24 },
        },
      },
    }),
  );
  renderApp();

  expect(
    await screen.findByRole("heading", { name: "Fetch in progress" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("progressbar")).toHaveAttribute("value", "24");
  expect(screen.getByRole("progressbar")).toHaveAttribute("max", "50");
  expect(screen.queryByText("Overview content")).not.toBeInTheDocument();
});

it("returns to the application after abandoning a failed fetch", async () => {
  const user = userEvent.setup();
  vi.mocked(getFetch).mockResolvedValue(
    buildFetchRun({ status: "failed", error: "source unavailable" }),
  );
  vi.mocked(abandonFetch).mockResolvedValue(
    buildFetchRun({ status: "abandoned" }),
  );
  renderApp();

  expect(
    await screen.findByRole("heading", { name: "Fetch failed" }),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "return to app" }));

  expect(abandonFetch).toHaveBeenCalledWith("fetch-one");
  expect(
    await screen.findByRole("heading", { name: "Overview content" }),
  ).toBeInTheDocument();
});

it("blocks the application when fetch status cannot be loaded", async () => {
  vi.mocked(getFetch).mockRejectedValue(new Error("unavailable"));
  renderApp();

  expect(
    await screen.findByText("Fetch status could not be loaded"),
  ).toBeInTheDocument();
  await waitFor(() => expect(getFetch).toHaveBeenCalledOnce());
});
