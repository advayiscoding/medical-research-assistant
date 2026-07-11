"use client";

// useParams() (client hook) returns params synchronously, sidestepping the
// Next 15+ async-params change that applies to Server Component page props.
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { ChatView } from "@/components/ChatView";
import { Spinner } from "@/components/ui";
import type { SessionDetail } from "@/lib/types";

export default function ChatSessionPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [session, setSession] = useState<SessionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getSession(params.id)
      .then(setSession)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          router.replace("/chat"); // unknown/foreign session
        } else {
          setError(err instanceof ApiError ? err.message : "Failed to load.");
        }
      });
  }, [params.id, router]);

  if (error) {
    return (
      <div className="flex h-dvh flex-col items-center justify-center gap-3">
        <p className="text-sm text-red-700">{error}</p>
        <Link href="/chat" className="text-sm text-[var(--color-primary)] hover:underline">
          Back to sessions
        </Link>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="flex h-dvh items-center justify-center">
        <Spinner label="Loading session…" />
      </div>
    );
  }

  return (
    <div className="flex h-dvh flex-col">
      <div className="flex items-center gap-3 border-b border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-3">
        <Link
          href="/chat"
          className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-muted)]"
          aria-label="Back to sessions"
        >
          <ArrowLeft size={18} aria-hidden />
        </Link>
        <h1 className="truncate font-sans text-sm font-semibold">{session.title}</h1>
      </div>
      <div className="flex-1">
        <ChatView sessionId={session.id} initialMessages={session.messages} />
      </div>
    </div>
  );
}
