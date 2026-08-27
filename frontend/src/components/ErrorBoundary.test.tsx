import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ErrorBoundary from "./ErrorBoundary";

function BrokenPage({ broken }: { broken: boolean }) {
  if (broken) throw new Error("render failed");
  return <h1>Recovered page</h1>;
}

it("contains a render failure and resets when the route changes", () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  const { rerender } = render(
    <ErrorBoundary resetKey="/reviews">
      <BrokenPage broken />
    </ErrorBoundary>,
  );
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Could not display this page",
  );
  rerender(
    <ErrorBoundary resetKey="/activity">
      <BrokenPage broken={false} />
    </ErrorBoundary>,
  );
  expect(
    screen.getByRole("heading", { name: "Recovered page" }),
  ).toBeInTheDocument();
});

it("retries the same route after its render failure clears", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  const user = userEvent.setup();
  const { rerender } = render(
    <ErrorBoundary resetKey="/reviews">
      <BrokenPage broken />
    </ErrorBoundary>,
  );
  rerender(
    <ErrorBoundary resetKey="/reviews">
      <BrokenPage broken={false} />
    </ErrorBoundary>,
  );
  await user.click(screen.getByRole("button", { name: "retry page" }));
  expect(
    screen.getByRole("heading", { name: "Recovered page" }),
  ).toBeInTheDocument();
});
