"use client";

import { ErrorFallback } from "@/components/ErrorFallback";

// Route-level boundary: app/chat/layout.tsx renders SessionSidebar as a sibling of
// this route segment's slot, so a crash caught here doesn't take the sidebar down.
export default function ChatSessionError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <ErrorFallback error={error} reset={reset} />;
}
