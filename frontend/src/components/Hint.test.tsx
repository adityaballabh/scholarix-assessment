import { fireEvent, render, screen } from "@testing-library/react";
import Hint from "./Hint";

it("stays open while either hovered or focused", () => {
  render(<Hint text="How this value is calculated" />);
  const hint = screen.getByRole("button", {
    name: "How this value is calculated",
  });

  fireEvent.pointerEnter(hint);
  fireEvent.focus(hint);
  fireEvent.pointerLeave(hint);
  expect(screen.getByText("How this value is calculated")).toBeInTheDocument();

  fireEvent.blur(hint);
  expect(screen.queryByText("How this value is calculated")).toBeNull();

  fireEvent.pointerEnter(hint);
  fireEvent.focus(hint);
  fireEvent.blur(hint);
  expect(screen.getByText("How this value is calculated")).toBeInTheDocument();

  fireEvent.pointerLeave(hint);
  expect(screen.queryByText("How this value is calculated")).toBeNull();
});
