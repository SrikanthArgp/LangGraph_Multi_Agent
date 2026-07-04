import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthProvider, useAuth } from "./AuthProvider";

const REFRESH_TOKEN_KEY = "crag_refresh_token";

const testUser = {
  id: "1",
  email: "alice@example.com",
  username: "alice",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function TestConsumer() {
  const { status, user, error, login, logout } = useAuth();
  return (
    <div>
      <p data-testid="status">{status}</p>
      <p data-testid="user">{user?.username ?? ""}</p>
      <p data-testid="error">{error ?? ""}</p>
      {/* login() rethrows on failure by design (so page-level callers can show a form
          error) - real callers always catch it, so the harness does too. */}
      <button onClick={() => login("alice@example.com", "password123").catch(() => {})}>
        login
      </button>
      <button onClick={() => void logout()}>logout</button>
    </div>
  );
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("AuthProvider", () => {
  it("resolves to unauthenticated when there is no stored refresh token", async () => {
    vi.stubGlobal("fetch", vi.fn());

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"),
    );
  });

  it("logs in, stores the refresh token, and exposes the user", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        tokens: { access_token: "at", refresh_token: "rt", token_type: "bearer", expires_in: 900 },
        user: testUser,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"),
    );

    await userEvent.click(screen.getByText("login"));

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(screen.getByTestId("user")).toHaveTextContent("alice");
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBe("rt");
  });

  it("surfaces a login failure as an error message, staying unauthenticated", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ detail: "Invalid email or password" }, 401));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"),
    );

    await userEvent.click(screen.getByText("login"));

    await waitFor(() =>
      expect(screen.getByTestId("error")).toHaveTextContent("Invalid email or password"),
    );
    expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated");
  });

  it("recovers a session on mount from the stored refresh token (silent refresh)", async () => {
    localStorage.setItem(REFRESH_TOKEN_KEY, "rt");
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/auth/refresh")) {
        return Promise.resolve(
          jsonResponse({
            access_token: "at",
            refresh_token: "rt2",
            token_type: "bearer",
            expires_in: 900,
          }),
        );
      }
      if (url.includes("/auth/me")) {
        return Promise.resolve(jsonResponse(testUser));
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(screen.getByTestId("user")).toHaveTextContent("alice");
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBe("rt2");
  });

  it("clears the refresh token and returns to unauthenticated when the stored one is invalid", async () => {
    localStorage.setItem(REFRESH_TOKEN_KEY, "stale-rt");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "Invalid or expired refresh token" }, 401)),
    );

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"),
    );
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull();
  });

  it("logout clears the refresh token and returns to unauthenticated", async () => {
    localStorage.setItem(REFRESH_TOKEN_KEY, "rt");
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/auth/refresh")) {
        return Promise.resolve(
          jsonResponse({
            access_token: "at",
            refresh_token: "rt2",
            token_type: "bearer",
            expires_in: 900,
          }),
        );
      }
      if (url.includes("/auth/me")) {
        return Promise.resolve(jsonResponse(testUser));
      }
      if (url.includes("/auth/logout")) {
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));

    await userEvent.click(screen.getByText("logout"));

    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"),
    );
    expect(screen.getByTestId("user")).toHaveTextContent("");
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull();
  });
});
