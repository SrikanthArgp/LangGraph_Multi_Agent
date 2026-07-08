"use client";

// Single route for both the empty state and an active chat, switched on a ?sessionId=
// search param rather than a [sessionId] path segment — see app/chat/layout.tsx's comment
// for why (static export can't pre-render arbitrary runtime session IDs as path segments).
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api";
import { streamChatMessage } from "@/lib/sse";
import { ChatMessage, type ChatMessageData } from "@/components/ChatMessage";
import { FullScreenMessage } from "@/components/FullScreenMessage";

interface MessageResponseWire {
  id: string;
  session_id: string;
  role: string;
  content: string;
  metadata: { web_search?: boolean } | null;
  created_at: string;
}

function fromWire(message: MessageResponseWire): ChatMessageData {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    createdAt: message.created_at,
    webSearch: Boolean(message.metadata?.web_search),
  };
}

type HistoryStatus = "loading" | "ready" | "not_found" | "error";

export default function ChatPage() {
  // useSearchParams requires a Suspense boundary in static-exported builds - see
  // app/chat/layout.tsx's SessionSidebar wrapping for the same requirement.
  return (
    <Suspense fallback={<FullScreenMessage>Loading…</FullScreenMessage>}>
      <ChatPageContent />
    </Suspense>
  );
}

function ChatPageContent() {
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("sessionId");

  if (!sessionId) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center">
        <p className="text-lg font-medium text-zinc-900 dark:text-zinc-50">No chat selected</p>
        <p className="max-w-sm text-sm text-zinc-500 dark:text-zinc-400">
          Pick a chat from the sidebar, or click “+ New” to start one.
        </p>
      </div>
    );
  }

  // Keyed by sessionId: switching chats should reset all local state (history, draft
  // input, streaming status) rather than carry it over, and a `key` gets that for free
  // via remount instead of a "reset state in an effect" anti-pattern.
  return <ChatSessionView key={sessionId} sessionId={sessionId} />;
}

function ChatSessionView({ sessionId }: { sessionId: string }) {
  const [historyStatus, setHistoryStatus] = useState<HistoryStatus>("loading");
  const [messages, setMessages] = useState<ChatMessageData[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const data = await apiFetch<{ messages: MessageResponseWire[] }>(
          `/sessions/${sessionId}/messages`,
        );
        if (cancelled) return;
        setMessages(data.messages.map(fromWire));
        setHistoryStatus("ready");
      } catch (err) {
        if (cancelled) return;
        setHistoryStatus(err instanceof ApiError && err.status === 404 ? "not_found" : "error");
      }
    })();

    return () => {
      cancelled = true;
      abortRef.current?.abort();
    };
  }, [sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = useCallback(async () => {
    const question = input.trim();
    if (!question || sending) return;

    setInput("");
    setStreamError(null);
    setSending(true);

    const userMessageId = `local-user-${Date.now()}`;
    const assistantMessageId = `local-assistant-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      { id: userMessageId, role: "user", content: question, createdAt: new Date().toISOString() },
      { id: assistantMessageId, role: "assistant", content: "", pending: true },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      for await (const event of streamChatMessage(sessionId, question, controller.signal)) {
        if (event.type === "token") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMessageId ? { ...m, content: m.content + event.token } : m,
            ),
          );
        } else if (event.type === "done") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMessageId
                ? { ...m, id: event.message_id, pending: false, createdAt: new Date().toISOString() }
                : m,
            ),
          );
        } else if (event.type === "error") {
          setStreamError(event.detail);
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantMessageId ? { ...m, pending: false } : m)),
          );
        }
      }
    } finally {
      setSending(false);
      abortRef.current = null;
    }
  }, [input, sending, sessionId]);

  if (historyStatus === "loading") {
    return <FullScreenMessage>Loading…</FullScreenMessage>;
  }

  if (historyStatus === "not_found") {
    return <FullScreenMessage>Chat not found.</FullScreenMessage>;
  }

  if (historyStatus === "error") {
    return <FullScreenMessage>Couldn&apos;t load this chat. Try reloading.</FullScreenMessage>;
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && (
          <p className="text-center text-sm text-zinc-500 dark:text-zinc-400">
            Ask something to get started.
          </p>
        )}
        {messages.map((message) => (
          <ChatMessage key={message.id} {...message} />
        ))}
        <div ref={bottomRef} />
      </div>

      {streamError && (
        <p
          role="alert"
          className="border-t border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300"
        >
          {streamError}
        </p>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void handleSend();
        }}
        className="flex gap-2 border-t border-zinc-200 p-3 dark:border-zinc-800"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question…"
          disabled={sending}
          className="flex-1 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/30 disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50"
        />
        <button
          type="submit"
          disabled={sending || !input.trim()}
          className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {sending ? "Sending…" : "Send"}
        </button>
      </form>
    </div>
  );
}
