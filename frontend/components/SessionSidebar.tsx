"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";

export interface SessionResponse {
  id: string;
  title: string | null;
  is_archived: boolean;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
}

function sessionLabel(session: SessionResponse): string {
  return session.title?.trim() || "New chat";
}

// GET /v1/sessions already caps results at the 5 most recent non-archived sessions
// server-side (cache/sessions.py's MAX_SESSIONS_PER_USER) - this component renders
// whatever it gets back without re-slicing.
export function SessionSidebar() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeSessionId = searchParams.get("sessionId") ?? undefined;
  const { user, logout } = useAuth();

  const [sessions, setSessions] = useState<SessionResponse[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [creating, setCreating] = useState(false);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const cancelRenameRef = useRef(false);

  const loadSessions = useCallback(async () => {
    try {
      const data = await apiFetch<{ sessions: SessionResponse[] }>("/sessions");
      setSessions(data.sessions);
      setStatus("ready");
    } catch {
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    void (async () => {
      await loadSessions();
    })();
  }, [loadSessions]);

  async function handleCreate() {
    setCreating(true);
    try {
      const session = await apiFetch<SessionResponse>("/sessions", {
        method: "POST",
        body: JSON.stringify({}),
      });
      setSessions((prev) => [session, ...prev]);
      router.push(`/chat?sessionId=${session.id}`);
    } catch {
      // Best-effort - the user can just click "+ New" again.
    } finally {
      setCreating(false);
    }
  }

  function startRename(session: SessionResponse) {
    setRenamingId(session.id);
    setRenameValue(sessionLabel(session));
  }

  async function commitRename(sessionId: string) {
    if (cancelRenameRef.current) {
      cancelRenameRef.current = false;
      return;
    }
    const title = renameValue.trim();
    setRenamingId(null);
    if (!title) return;
    try {
      const updated = await apiFetch<SessionResponse>(`/sessions/${sessionId}`, {
        method: "PATCH",
        body: JSON.stringify({ title }),
      });
      setSessions((prev) => prev.map((s) => (s.id === sessionId ? updated : s)));
    } catch {
      // Best-effort - a failed rename just leaves the old title in place.
    }
  }

  async function handleDelete(sessionId: string) {
    if (!window.confirm("Delete this chat? This can't be undone from here.")) return;
    try {
      await apiFetch<void>(`/sessions/${sessionId}`, { method: "DELETE" });
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (activeSessionId === sessionId) router.push("/chat");
    } catch {
      // Best-effort - leave the session in the list so the user can retry.
    }
  }

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-center justify-between p-3">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Chats</h2>
        <button
          onClick={() => void handleCreate()}
          disabled={creating}
          className="rounded-md bg-emerald-600 px-2 py-1 text-xs font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          + New
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2">
        {status === "loading" && (
          <p className="p-2 text-xs text-zinc-500 dark:text-zinc-400">Loading…</p>
        )}
        {status === "error" && (
          <p role="alert" className="p-2 text-xs text-red-600 dark:text-red-400">
            Couldn&apos;t load chats.
          </p>
        )}
        {status === "ready" && sessions.length === 0 && (
          <p className="p-2 text-xs text-zinc-500 dark:text-zinc-400">No chats yet.</p>
        )}

        <ul className="space-y-1">
          {sessions.map((session) => {
            const isActive = session.id === activeSessionId;
            // data-testid is on the <li> since its text content swaps between the title
            // label and a rename <input> - e2e tests need a stable target.
            return (
              <li key={session.id} data-testid="session-item">
                {renamingId === session.id ? (
                  <input
                    autoFocus
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onBlur={() => void commitRename(session.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") e.currentTarget.blur();
                      if (e.key === "Escape") {
                        cancelRenameRef.current = true;
                        setRenamingId(null);
                      }
                    }}
                    className="w-full rounded-md border border-emerald-600 bg-white px-2 py-1.5 text-sm outline-none dark:bg-zinc-900"
                  />
                ) : (
                  <div
                    className={`group flex items-center gap-1 rounded-md px-2 py-1.5 ${
                      isActive
                        ? "bg-emerald-100 dark:bg-emerald-900/40"
                        : "hover:bg-zinc-200 dark:hover:bg-zinc-800"
                    }`}
                  >
                    <button
                      onClick={() => router.push(`/chat?sessionId=${session.id}`)}
                      className="flex-1 truncate text-left text-sm text-zinc-800 dark:text-zinc-200"
                      title={sessionLabel(session)}
                    >
                      {sessionLabel(session)}
                    </button>
                    <button
                      onClick={() => startRename(session)}
                      aria-label="Rename chat"
                      className="hidden rounded p-1 text-xs text-zinc-500 hover:bg-zinc-300 group-hover:block dark:text-zinc-400 dark:hover:bg-zinc-700"
                    >
                      ✎
                    </button>
                    <button
                      onClick={() => void handleDelete(session.id)}
                      aria-label="Delete chat"
                      className="hidden rounded p-1 text-xs text-zinc-500 hover:bg-zinc-300 group-hover:block dark:text-zinc-400 dark:hover:bg-zinc-700"
                    >
                      🗑
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </div>

      <div className="border-t border-zinc-200 p-3 dark:border-zinc-800">
        <p className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-50">
          {user?.username}
        </p>
        <button
          onClick={() => void logout()}
          className="mt-2 w-full rounded-md border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
        >
          Log out
        </button>
      </div>
    </aside>
  );
}
