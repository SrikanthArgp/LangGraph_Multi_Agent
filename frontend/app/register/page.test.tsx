import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthProvider } from "@/components/AuthProvider";
import { ThemeProvider } from "@/components/ThemeProvider";
import RegisterPage from "./page";

// RegisterPage renders a ThemeToggle, which needs a ThemeProvider ancestor.
function renderRegisterPage() {
  return render(
    <ThemeProvider>
      <AuthProvider>
        <RegisterPage />
      </AuthProvider>
    </ThemeProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("RegisterPage", () => {
  it("submits email, username, and password to /auth/register", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          tokens: {
            access_token: "at",
            refresh_token: "rt",
            token_type: "bearer",
            expires_in: 900,
          },
          user: {
            id: "1",
            email: "alice@example.com",
            username: "alice",
            is_active: true,
            created_at: "2026-01-01T00:00:00Z",
          },
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderRegisterPage();

    await userEvent.type(screen.getByLabelText("Email"), "alice@example.com");
    await userEvent.type(screen.getByLabelText("Username"), "alice");
    await userEvent.type(screen.getByLabelText("Password"), "password123");
    await userEvent.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const call = fetchMock.mock.calls.find((args: unknown[]) =>
      (args[0] as string).includes("/auth/register"),
    );
    expect(call).toBeDefined();
    const [, init] = call!;
    expect(JSON.parse(init.body as string)).toEqual({
      email: "alice@example.com",
      username: "alice",
      password: "password123",
    });
  });

  it("shows a form error instead of crashing on a failed registration", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Email or username already registered" }), {
          status: 409,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    renderRegisterPage();

    await userEvent.type(screen.getByLabelText("Email"), "alice@example.com");
    await userEvent.type(screen.getByLabelText("Username"), "alice");
    await userEvent.type(screen.getByLabelText("Password"), "password123");
    await userEvent.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Email or username already registered"),
    );
  });
});
