import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import GlobalErrorBoundary from "./error";

describe("GlobalErrorBoundary", () => {
  it("renders the fallback UI for a render-phase crash instead of a blank page", () => {
    const error = Object.assign(new Error("boom"), { digest: "abc123" });

    render(<GlobalErrorBoundary error={error} reset={vi.fn()} />);

    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("calls reset() when the retry button is clicked", async () => {
    const reset = vi.fn();
    const error = Object.assign(new Error("boom"), { digest: "abc123" });

    render(<GlobalErrorBoundary error={error} reset={reset} />);
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));

    expect(reset).toHaveBeenCalledTimes(1);
  });
});
