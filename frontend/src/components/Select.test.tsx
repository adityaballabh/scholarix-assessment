import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Select from "./Select";

const STATUS_OPTIONS = [
  { value: "pending", label: "pending" },
  { value: "needs_split", label: "needs split" },
  { value: "deferred", label: "deferred" },
] as const;

it("chooses an option with the keyboard and returns focus", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  render(
    <Select
      label="Status"
      value="pending"
      options={[...STATUS_OPTIONS]}
      onChange={onChange}
    />,
  );

  const trigger = screen.getByRole("button", { name: "Status: pending" });
  await user.click(trigger);
  const listbox = screen.getByRole("listbox", { name: "Status" });
  await user.keyboard("{ArrowDown}{Enter}");

  expect(onChange).toHaveBeenCalledWith("needs_split");
  expect(listbox).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});

it("supports typeahead without changing the value immediately", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  render(
    <Select
      label="Status"
      value="pending"
      options={[...STATUS_OPTIONS]}
      onChange={onChange}
    />,
  );

  await user.click(screen.getByRole("button", { name: "Status: pending" }));
  await user.keyboard("d");

  const listbox = screen.getByRole("listbox", { name: "Status" });
  expect(listbox).toHaveAttribute(
    "aria-activedescendant",
    screen.getByRole("option", { name: "deferred" }).id,
  );
  expect(onChange).not.toHaveBeenCalled();
});
