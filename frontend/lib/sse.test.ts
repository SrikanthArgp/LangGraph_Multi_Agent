import { streamChatMessage, type ChatStreamEvent } from "./sse";
import { setAccessToken } from "./api";

function streamFromChunks(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

function sseResponse(chunks: string[], status = 200): Response {
  return new Response(streamFromChunks(chunks), {
    status,
    headers: { "Content-Type": "text/event-stream" },
  });
}

async function collect(sessionId: string, question: string): Promise<ChatStreamEvent[]> {
  const events: ChatStreamEvent[] = [];
  for await (const event of streamChatMessage(sessionId, question)) {
    events.push(event);
  }
  return events;
}

beforeEach(() => {
  setAccessToken("token");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("streamChatMessage", () => {
  it("parses a multi-chunk stream into token then done events, split mid-frame", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        sseResponse([
          'data: {"type":"token","token":"Hel',
          'lo"}\n\n',
          'data: {"type":"done","message_id":"m1"}\n\n',
        ]),
      ),
    );

    const events = await collect("s1", "hi");

    expect(events).toEqual([
      { type: "token", token: "Hello" },
      { type: "done", message_id: "m1" },
    ]);
  });

  it("attaches the Authorization header and question as a query param", async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseResponse(['data: {"type":"done","message_id":"m1"}\n\n']));
    vi.stubGlobal("fetch", fetchMock);

    await collect("session-42", "what is CRAG?");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/sessions/session-42/stream?question=what%20is%20CRAG%3F");
    expect((init.headers as Headers).get("Authorization")).toBe("Bearer token");
  });

  it("surfaces a non-2xx response as an error event instead of throwing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 404 })));

    const events = await collect("missing-session", "hi");

    expect(events).toEqual([{ type: "error", detail: "Request failed with status 404" }]);
  });

  it("surfaces a network failure as an error event instead of an unhandled rejection", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    const events = await collect("s1", "hi");

    expect(events).toEqual([
      { type: "error", detail: "Network error — check your connection and try again." },
    ]);
  });

  it("surfaces a stream that closes without a done/error frame as an error event", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(sseResponse(['data: {"type":"token","token":"partial"}\n\n'])),
    );

    const events = await collect("s1", "hi");

    expect(events).toEqual([
      { type: "token", token: "partial" },
      { type: "error", detail: "The connection closed unexpectedly, please try again." },
    ]);
  });

  it("surfaces a reader that throws mid-stream as an error event", async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('data: {"type":"token","token":"a"}\n\n'));
      },
      pull() {
        throw new Error("connection reset");
      },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(stream, { headers: { "Content-Type": "text/event-stream" } })),
    );

    const events = await collect("s1", "hi");

    expect(events.at(-1)).toEqual({
      type: "error",
      detail: "The connection was interrupted, please try again.",
    });
  });
});
