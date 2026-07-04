import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthProvider } from "@/components/AuthProvider";
import LoginPage from "./page";

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("LoginPage", () => {
  it("shows a form error instead of crashing when the network is down", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );

    await userEvent.type(screen.getByLabelText("Email"), "alice@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "password123");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/network error/i),
    );
    // The form itself must still be there - a crash would have unmounted it.
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("shows the server's message on invalid credentials", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Invalid email or password" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );

    await userEvent.type(screen.getByLabelText("Email"), "alice@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Invalid email or password"),
    );
  });
});
