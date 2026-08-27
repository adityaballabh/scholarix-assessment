import { fireEvent, render, screen } from "@testing-library/react";
import Hint from "./Hint";

const TEXT = "Share of matching publications";

it("stays open until both pointer and focus leave", () => {
  render(<Hint text={TEXT} />);
  const trigger = screen.getByRole("button", { name: TEXT });
  fireEvent.pointerEnter(trigger);
  fireEvent.focus(trigger);
  fireEvent.pointerLeave(trigger);
  expect(screen.getByText(TEXT)).toBeInTheDocument();
  fireEvent.blur(trigger);
  expect(screen.queryByText(TEXT)).toBeNull();

  fireEvent.pointerEnter(trigger);
  fireEvent.focus(trigger);
  fireEvent.blur(trigger);
  expect(screen.getByText(TEXT)).toBeInTheDocument();
  fireEvent.pointerLeave(trigger);
  expect(screen.queryByText(TEXT)).toBeNull();
});

it("Escape dismisses until both interactions end, then allows reopening", () => {
  render(<Hint text={TEXT} />);
  const trigger = screen.getByRole("button", { name: TEXT });
  fireEvent.focus(trigger);
  fireEvent.pointerEnter(trigger);
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByText(TEXT)).toBeNull();
  fireEvent.pointerLeave(trigger);
  expect(screen.queryByText(TEXT)).toBeNull();
  fireEvent.blur(trigger);
  fireEvent.pointerEnter(trigger);
  expect(screen.getByText(TEXT)).toBeInTheDocument();
});

it("dismisses a hover-only hint with Escape", () => {
  render(<Hint text={TEXT} />);
  fireEvent.pointerEnter(screen.getByRole("button", { name: TEXT }));
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByText(TEXT)).toBeNull();
});
