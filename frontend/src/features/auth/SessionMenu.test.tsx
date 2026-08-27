import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { REVIEWER } from "../../test/data";
import { SessionMenu } from "./SessionMenu";

it("acts as a disclosure and returns focus on Escape", async () => {
  const user = userEvent.setup();
  render(<SessionMenu user={REVIEWER} onSignOut={vi.fn()} />);
  const trigger = screen.getByRole("button", { name: REVIEWER.display_name });
  await user.click(trigger);
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  expect(screen.queryByRole("menu")).toBeNull();
  await user.tab();
  expect(screen.getByRole("button", { name: "sign out" })).toHaveFocus();
  await user.keyboard("{Escape}");
  expect(trigger).toHaveFocus();
  expect(trigger).toHaveAttribute("aria-expanded", "false");
});

it("keeps failure feedback visible and allows another sign-out attempt", async () => {
  const user = userEvent.setup();
  const signOut = vi
    .fn()
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValue(undefined);
  render(<SessionMenu user={REVIEWER} onSignOut={signOut} />);
  await user.click(screen.getByRole("button", { name: REVIEWER.display_name }));
  await user.click(screen.getByRole("button", { name: "sign out" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Could not sign out. Try again",
  );
  expect(
    screen.getByRole("button", { name: REVIEWER.display_name }),
  ).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "sign out" }));
  expect(signOut).toHaveBeenCalledTimes(2);
  expect(screen.queryByRole("button", { name: "sign out" })).toBeNull();
});

it("closes when keyboard focus leaves the disclosure", async () => {
  const user = userEvent.setup();
  render(
    <>
      <SessionMenu user={REVIEWER} onSignOut={vi.fn()} />
      <button>next control</button>
    </>,
  );
  await user.click(screen.getByRole("button", { name: REVIEWER.display_name }));
  await user.tab();
  await user.tab();
  expect(screen.getByRole("button", { name: "next control" })).toHaveFocus();
  expect(screen.queryByRole("button", { name: "sign out" })).toBeNull();
});
