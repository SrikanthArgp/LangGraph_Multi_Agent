"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { FullScreenMessage } from "@/components/FullScreenMessage";

// Route guard: middleware/proxy can't see this app's auth state (access token lives only
// in memory, refresh token in localStorage — neither is readable server-side), so
// protection has to happen here, client-side, once AuthProvider resolves its status.
export default function ChatLayout({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "unauthenticated") router.replace("/login");
  }, [status, router]);

  if (status !== "authenticated") {
    return <FullScreenMessage>Loading…</FullScreenMessage>;
  }

  return <>{children}</>;
}
