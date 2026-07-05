"use client";

import { useEffect } from "react";

// Shared by app/error.tsx (root boundary) and app/chat/[sessionId]/error.tsx
// (route-level boundary) - same fallback UI, different scope of what they catch.
export function ErrorFallback({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
      <h2 className="text-lg font-semibold">Something went wrong</h2>
      <p className="max-w-sm text-sm text-zinc-500 dark:text-zinc-400">
        An unexpected error occurred. You can try again, or reload the page if the problem
        persists.
      </p>
      <button
        onClick={() => reset()}
        className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-50 dark:text-zinc-900 dark:hover:bg-zinc-200"
      >
        Try again
      </button>
    </div>
  );
}
