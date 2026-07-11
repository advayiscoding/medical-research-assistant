"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Plus, MessagesSquare } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { Button, Card, Spinner } from "@/components/ui";
import type { ChatSession } from "@/lib/types";

export default function ChatListPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    api
      .listSessions()
      .then(setSessions)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  async function newSession() {
    setCreating(true);
    try {
      const s = await api.createSession();
      router.push(`/chat/${s.id}`);
    } catch (err) {
      if (err instanceof ApiError) alert(err.message);
      setCreating(false);
    }
  }

  return (
    <div className="flex h-dvh flex-col">
      <PageHeader
        title="Chat"
        subtitle="Continue a research session or start a new one."
        action={
          <Button onClick={newSession} disabled={creating}>
            <Plus size={16} aria-hidden />
            New session
          </Button>
        }
      />
      <div className="flex-1 overflow-y-auto px-8 py-6">
        {loading ? (
          <Spinner label="Loading sessions…" />
        ) : sessions.length === 0 ? (
          <div className="mt-16 flex flex-col items-center text-center text-[var(--color-muted-foreground)]">
            <MessagesSquare size={40} className="mb-3 opacity-50" aria-hidden />
            <p className="font-sans text-lg font-medium text-[var(--color-foreground)]">
              No sessions yet
            </p>
            <p className="mt-1 text-sm">Start a session to ask your first question.</p>
            <Button onClick={newSession} disabled={creating} className="mt-4">
              <Plus size={16} aria-hidden />
              New session
            </Button>
          </div>
        ) : (
          <div className="space-y-2">
            {sessions.map((s) => (
              <Link key={s.id} href={`/chat/${s.id}`}>
                <Card className="flex items-center justify-between p-4 transition-colors hover:border-[var(--color-primary)]">
                  <div className="flex items-center gap-3">
                    <MessagesSquare size={18} className="text-[var(--color-primary)]" aria-hidden />
                    <span className="text-sm font-medium">{s.title}</span>
                  </div>
                  <span className="text-xs text-[var(--color-muted-foreground)]">
                    {new Date(s.updated_at).toLocaleString()}
                  </span>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
