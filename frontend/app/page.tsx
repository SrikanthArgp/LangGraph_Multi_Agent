"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { FullScreenMessage } from "@/components/FullScreenMessage";

export default function Home() {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "authenticated") router.replace("/chat");
    else if (status === "unauthenticated") router.replace("/login");
  }, [status, router]);

  return <FullScreenMessage>Loading…</FullScreenMessage>;
}
