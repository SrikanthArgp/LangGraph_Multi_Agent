"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { FullScreenMessage } from "@/components/FullScreenMessage";
import { SessionSidebar } from "@/components/SessionSidebar";

// Route guard: middleware/proxy can't see this app's auth state (access token lives only
// in memory, refresh token in localStorage — neither is readable server-side), so
// protection has to happen here, client-side, once AuthProvider resolves its status.
// The sidebar lives here (not in each page) so it's shared, and stays mounted, across
// both /chat (empty state) and /chat/[sessionId] (a route-level error.tsx boundary there
// means a crash rendering one chat doesn't take this sidebar down with it).
export default function ChatLayout({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "unauthenticated") router.replace("/login");
  }, [status, router]);

  if (status !== "authenticated") {
    return <FullScreenMessage>Loading…</FullScreenMessage>;
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      <SessionSidebar />
      <div className="flex flex-1 flex-col overflow-hidden">{children}</div>
    </div>
  );
}
