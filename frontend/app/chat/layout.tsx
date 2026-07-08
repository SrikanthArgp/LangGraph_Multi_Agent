"use client";

import { Suspense, useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { FullScreenMessage } from "@/components/FullScreenMessage";
import { SessionSidebar } from "@/components/SessionSidebar";

// Route guard: middleware/proxy can't see this app's auth state (access token lives only
// in memory, refresh token in localStorage — neither is readable server-side), so
// protection has to happen here, client-side, once AuthProvider resolves its status.
// The sidebar lives here (not in the page) so it's shared, and stays mounted, across both
// the empty state and an active chat (app/chat/error.tsx's route-level boundary means a
// crash rendering one chat doesn't take this sidebar down with it) — both are the same
// /chat route now, switched on a ?sessionId= search param rather than a [sessionId] path
// segment, since a dynamic path segment can't be statically exported for arbitrary
// runtime session IDs (see enterprize-deploy-steps.md Stage A step 5).
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
      {/* SessionSidebar reads ?sessionId= via useSearchParams, which requires a Suspense
          boundary during static export builds (Next.js "Missing Suspense boundary with
          useSearchParams" build error otherwise). */}
      <Suspense fallback={null}>
        <SessionSidebar />
      </Suspense>
      <div className="flex flex-1 flex-col overflow-hidden">{children}</div>
    </div>
  );
}
