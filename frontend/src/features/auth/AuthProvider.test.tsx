import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  createAccount,
  getCurrentUser,
  setUnauthorizedHandler,
} from "../../api/client";
import { REVIEWER } from "../../test/data";
import { AuthProvider, useSession } from "./AuthProvider";

const clientState = vi.hoisted(() => ({
  unauthorizedHandler: null as (() => Promise<boolean>) | null,
}));

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  createAccount: vi.fn(),
  getCurrentUser: vi.fn(),
  setUnauthorizedHandler: vi.fn((handler: (() => Promise<boolean>) | null) => {
    clientState.unauthorizedHandler = handler;
  }),
  signIn: vi.fn(),
  signOut: vi.fn(),
}));

function SessionState() {
  const { ready, user } = useSession();
  return <p>{ready ? (user?.display_name ?? "signed out") : "loading"}</p>;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getCurrentUser).mockRejectedValue(new Error("signed out"));
  clientState.unauthorizedHandler = null;
});

it("lets a reviewer dismiss an unauthorized write", async () => {
  const user = userEvent.setup();
  render(
    <AuthProvider>
      <SessionState />
    </AuthProvider>,
  );
  expect(await screen.findByText("signed out")).toBeInTheDocument();
  expect(setUnauthorizedHandler).toHaveBeenCalled();

  let result!: Promise<boolean>;
  act(() => {
    result = clientState.unauthorizedHandler!();
  });
  const dialog = await screen.findByRole("dialog", { name: "Sign in" });
  await user.click(within(dialog).getByRole("button", { name: "Close" }));

  await expect(result).resolves.toBe(false);
  expect(screen.queryByRole("dialog", { name: "Sign in" })).toBeNull();
});

it("resumes an unauthorized write after account creation", async () => {
  const user = userEvent.setup();
  vi.mocked(createAccount).mockResolvedValue(REVIEWER);
  render(
    <AuthProvider>
      <SessionState />
    </AuthProvider>,
  );
  await screen.findByText("signed out");

  let result!: Promise<boolean>;
  act(() => {
    result = clientState.unauthorizedHandler!();
  });
  const dialog = await screen.findByRole("dialog", { name: "Sign in" });
  await user.type(within(dialog).getByLabelText("username"), "  REVIEWER  ");
  await user.type(
    within(dialog).getByLabelText("display name"),
    "  Test Reviewer  ",
  );
  await user.type(within(dialog).getByLabelText("password"), "correct horse");
  await user.click(
    within(dialog).getByRole("button", { name: "create account" }),
  );

  expect(createAccount).toHaveBeenCalledWith({
    username: "reviewer",
    display_name: "Test Reviewer",
    password: "correct horse",
  });
  await expect(result).resolves.toBe(true);
  expect(await screen.findByText(REVIEWER.display_name)).toBeInTheDocument();
});

it("shows registration validation before calling the API", async () => {
  const user = userEvent.setup();
  render(
    <AuthProvider>
      <SessionState />
    </AuthProvider>,
  );
  await screen.findByText("signed out");

  act(() => {
    void clientState.unauthorizedHandler!();
  });
  const dialog = await screen.findByRole("dialog", { name: "Sign in" });
  await user.type(within(dialog).getByLabelText("username"), "rj");
  await user.type(within(dialog).getByLabelText("display name"), "rj");
  await user.type(within(dialog).getByLabelText("password"), "correct horse");
  await user.click(
    within(dialog).getByRole("button", { name: "create account" }),
  );

  expect(
    within(dialog).getByText("Username must be at least 3 characters"),
  ).toHaveAttribute("role", "alert");
  expect(createAccount).not.toHaveBeenCalled();
});
