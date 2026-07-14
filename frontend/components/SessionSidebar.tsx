"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";
import { ThemeToggle } from "@/components/ThemeToggle";
import { LogoutIcon, PencilIcon, PlusIcon, TrashIcon } from "@/components/icons";

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

  const initial = user?.username?.trim().charAt(0).toUpperCase() || "?";

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950">
      {/* Brand - fixed, never scrolls. */}
      <div className="flex items-center gap-2 px-4 pt-4 pb-1">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-emerald-600 text-xs font-semibold text-white">
          C
        </div>
        <span className="truncate text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          CRAG Assistant
        </span>
      </div>

      {/* New chat - fixed, per the brief: only the session list below scrolls. */}
      <div className="px-3 pt-3 pb-2">
        <button
          onClick={() => void handleCreate()}
          disabled={creating}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm font-medium text-zinc-700 shadow-sm transition-colors hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
        >
          <PlusIcon className="h-4 w-4 text-emerald-600 dark:text-emerald-500" />
          New chat
        </button>
      </div>

      <div className="px-4 pt-2 pb-1 text-xs font-medium tracking-wide text-zinc-400 uppercase dark:text-zinc-500">
        Recent
      </div>

      {/* Only this list scrolls. */}
      <div className="scroll-thin flex-1 overflow-y-auto px-2 pb-2">
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

        <ul className="space-y-0.5">
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
                      className={`flex-1 truncate text-left text-sm ${
                        isActive
                          ? "font-medium text-emerald-800 dark:text-emerald-200"
                          : "text-zinc-700 dark:text-zinc-300"
                      }`}
                      title={sessionLabel(session)}
                    >
                      {sessionLabel(session)}
                    </button>
                    <button
                      onClick={() => startRename(session)}
                      aria-label="Rename chat"
                      className="hidden shrink-0 rounded p-1 text-zinc-500 hover:bg-zinc-300 group-hover:block dark:text-zinc-400 dark:hover:bg-zinc-700"
                    >
                      <PencilIcon className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() => void handleDelete(session.id)}
                      aria-label="Delete chat"
                      className="hidden shrink-0 rounded p-1 text-zinc-500 hover:bg-zinc-300 group-hover:block dark:text-zinc-400 dark:hover:bg-zinc-700"
                    >
                      <TrashIcon className="h-3.5 w-3.5" />
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </div>

      {/* User + logout - fixed at the bottom-left of the shell, never scrolls. */}
      <div className="border-t border-zinc-200 p-3 dark:border-zinc-800">
        <div className="mb-2 flex items-center gap-2">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-zinc-300 text-xs font-semibold text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200">
            {initial}
          </div>
          <p className="flex-1 truncate text-sm font-medium text-zinc-900 dark:text-zinc-50">
            {user?.username}
          </p>
          <ThemeToggle />
        </div>
        <button
          onClick={() => void logout()}
          className="flex w-full items-center justify-center gap-1.5 rounded-md border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
        >
          <LogoutIcon className="h-3.5 w-3.5" />
          Log out
        </button>
      </div>
    </aside>
  );
}
