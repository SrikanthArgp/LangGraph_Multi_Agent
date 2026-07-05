import { fetchWithAuth } from "@/lib/api";

// Matches backend/api/schemas/chat.py's TokenEvent/DoneEvent/ErrorEvent - one JSON object
// per "data: ..." SSE frame.
export interface TokenEvent {
  type: "token";
  token: string;
}

export interface DoneEvent {
  type: "done";
  message_id: string;
}

export interface ErrorEvent {
  type: "error";
  detail: string;
}

export type ChatStreamEvent = TokenEvent | DoneEvent | ErrorEvent;

function parseFrame(rawFrame: string): ChatStreamEvent | null {
  const dataLines = rawFrame
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trim());
  if (dataLines.length === 0) return null;

  try {
    const payload = JSON.parse(dataLines.join("\n"));
    if (payload && typeof payload === "object" && typeof payload.type === "string") {
      return payload as ChatStreamEvent;
    }
  } catch {
    // Malformed frame - swallowed here, surfaced by the caller as the "no terminal event
    // seen" case below rather than throwing out of the generator.
  }
  return null;
}

// Native EventSource can't send the Authorization header this app relies on (see
// plan.md's Phase 8 streaming note), so this consumes GET .../stream by hand via
// fetch + ReadableStream. Never throws - every failure mode (network error, non-2xx,
// a reader that throws mid-stream, or a connection that closes without a done/error
// frame) is surfaced as a `{type: "error"}` event instead, since that's already part
// of the SSE event contract the UI understands.
export async function* streamChatMessage(
  sessionId: string,
  question: string,
  signal?: AbortSignal,
): AsyncGenerator<ChatStreamEvent> {
  let response: Response;
  try {
    response = await fetchWithAuth(
      `/sessions/${sessionId}/stream?question=${encodeURIComponent(question)}`,
      { signal },
    );
  } catch {
    yield { type: "error", detail: "Network error — check your connection and try again." };
    return;
  }

  if (!response.ok || !response.body) {
    yield { type: "error", detail: `Request failed with status ${response.status}` };
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sawTerminalEvent = false;

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let separatorIndex: number;
      while ((separatorIndex = buffer.indexOf("\n\n")) !== -1) {
        const rawFrame = buffer.slice(0, separatorIndex);
        buffer = buffer.slice(separatorIndex + 2);
        const event = parseFrame(rawFrame);
        if (event) {
          if (event.type === "done" || event.type === "error") sawTerminalEvent = true;
          yield event;
        }
      }
    }
  } catch {
    yield { type: "error", detail: "The connection was interrupted, please try again." };
    return;
  }

  if (!sawTerminalEvent) {
    yield { type: "error", detail: "The connection closed unexpectedly, please try again." };
  }
}
