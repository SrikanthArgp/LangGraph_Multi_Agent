"use client";

import { useAuth } from "@/components/AuthProvider";

// Placeholder landing spot behind the auth guard — the real session sidebar and
// streaming chat UI are built in Phase 8, on top of this phase's auth plumbing.
export default function ChatHomePage() {
  const { user, logout } = useAuth();

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
      <p className="text-sm text-zinc-500 dark:text-zinc-400">Signed in as</p>
      <p className="text-lg font-medium text-zinc-900 dark:text-zinc-50">{user?.username}</p>
      <p className="max-w-sm text-sm text-zinc-500 dark:text-zinc-400">
        The chat interface arrives in Phase 8. For now this page confirms auth, session
        persistence across reloads, and logout all work end to end.
      </p>
      <button
        onClick={() => void logout()}
        className="rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
      >
        Log out
      </button>
    </div>
  );
}
