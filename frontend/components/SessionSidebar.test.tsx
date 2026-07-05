import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SessionSidebar } from "./SessionSidebar";
import { setAccessToken } from "@/lib/api";

vi.mock("@/components/AuthProvider", () => ({
  useAuth: () => ({
    user: { id: "u1", email: "alice@example.com", username: "alice", is_active: true },
    logout: vi.fn(),
  }),
}));

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const session1 = {
  id: "s1",
  title: "First chat",
  is_archived: false,
  last_message_at: "2026-01-02T00:00:00Z",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
};
const session2 = {
  id: "s2",
  title: null,
  is_archived: false,
  last_message_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  setAccessToken("token");
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("SessionSidebar", () => {
  it("renders the sessions returned by GET /sessions", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ sessions: [session1, session2] })),
    );

    render(<SessionSidebar />);

    expect(await screen.findByText("First chat")).toBeInTheDocument();
    expect(screen.getByText("New chat")).toBeInTheDocument();
  });

  it("shows an error state when the list fails to load", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "boom" }, 500)));

    render(<SessionSidebar />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't load/i);
  });

  it("creates a new session via POST /sessions and adds it to the list", async () => {
    const created = { ...session2, id: "s3" };
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST") return Promise.resolve(jsonResponse(created, 201));
      return Promise.resolve(jsonResponse({ sessions: [session1] }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SessionSidebar />);
    await screen.findByText("First chat");

    await userEvent.click(screen.getByText("+ New"));

    await waitFor(() => expect(screen.getAllByText("New chat")).toHaveLength(1));
    const [, postInit] = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(postInit).toMatchObject({ method: "POST" });
  });

  it("renames a session via PATCH /sessions/{id} and updates the displayed title", async () => {
    const renamed = { ...session1, title: "Renamed chat" };
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "PATCH") return Promise.resolve(jsonResponse(renamed));
      return Promise.resolve(jsonResponse({ sessions: [session1] }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SessionSidebar />);
    const row = (await screen.findByText("First chat")).closest("div")!;
    await userEvent.click(within(row).getByLabelText("Rename chat"));

    const input = screen.getByDisplayValue("First chat");
    await userEvent.clear(input);
    await userEvent.type(input, "Renamed chat{Enter}");

    await waitFor(() => expect(screen.getByText("Renamed chat")).toBeInTheDocument());
    const [patchUrl, patchInit] = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH")!;
    expect(patchUrl).toContain("/sessions/s1");
    expect(JSON.parse(patchInit!.body as string)).toEqual({ title: "Renamed chat" });
  });

  it("deletes (archives) a session via DELETE /sessions/{id} and removes it from the list", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "DELETE") return Promise.resolve(new Response(null, { status: 204 }));
      return Promise.resolve(jsonResponse({ sessions: [session1] }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SessionSidebar />);
    const row = (await screen.findByText("First chat")).closest("div")!;
    await userEvent.click(within(row).getByLabelText("Delete chat"));

    await waitFor(() => expect(screen.queryByText("First chat")).not.toBeInTheDocument());
    const [deleteUrl] = fetchMock.mock.calls.find(([, init]) => init?.method === "DELETE")!;
    expect(deleteUrl).toContain("/sessions/s1");
  });

  it("does not delete when the confirmation dialog is cancelled", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ sessions: [session1] }));
    vi.stubGlobal("fetch", fetchMock);

    render(<SessionSidebar />);
    const row = (await screen.findByText("First chat")).closest("div")!;
    await userEvent.click(within(row).getByLabelText("Delete chat"));

    expect(screen.getByText("First chat")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(false);
  });
});
