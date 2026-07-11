"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Search, MessagesSquare, Clock } from "lucide-react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { Card, Spinner } from "@/components/ui";
import type { ChatSession, SearchHistoryItem } from "@/lib/types";

export default function HistoryPage() {
  const [searches, setSearches] = useState<SearchHistoryItem[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.allSettled([api.searchHistory(), api.listSessions()])
      .then(([s, c]) => {
        if (s.status === "fulfilled") setSearches(s.value);
        if (c.status === "fulfilled") setSessions(c.value);
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="flex h-dvh flex-col">
      <PageHeader title="Research history" subtitle="Your past searches and chat sessions." />
      <div className="flex-1 overflow-y-auto px-8 py-6">
        {loading ? (
          <Spinner label="Loading history…" />
        ) : (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <section>
              <h2 className="mb-3 flex items-center gap-2 font-sans text-sm font-semibold uppercase tracking-wide text-[var(--color-muted-foreground)]">
                <Search size={14} aria-hidden /> Searches
              </h2>
              {searches.length === 0 ? (
                <p className="text-sm text-[var(--color-muted-foreground)]">No searches yet.</p>
              ) : (
                <Card className="divide-y divide-[var(--color-border)]">
                  {searches.map((s) => (
                    <div key={s.id} className="flex items-center justify-between px-4 py-3">
                      <span className="truncate text-sm">{s.query}</span>
                      <span className="ml-3 flex shrink-0 items-center gap-1 text-xs text-[var(--color-muted-foreground)]">
                        {s.result_count} results
                      </span>
                    </div>
                  ))}
                </Card>
              )}
            </section>

            <section>
              <h2 className="mb-3 flex items-center gap-2 font-sans text-sm font-semibold uppercase tracking-wide text-[var(--color-muted-foreground)]">
                <MessagesSquare size={14} aria-hidden /> Chat sessions
              </h2>
              {sessions.length === 0 ? (
                <p className="text-sm text-[var(--color-muted-foreground)]">No sessions yet.</p>
              ) : (
                <Card className="divide-y divide-[var(--color-border)]">
                  {sessions.map((s) => (
                    <Link
                      key={s.id}
                      href={`/chat/${s.id}`}
                      className="flex items-center justify-between px-4 py-3 transition-colors hover:bg-[var(--color-surface-muted)]"
                    >
                      <span className="truncate text-sm">{s.title}</span>
                      <span className="ml-3 flex shrink-0 items-center gap-1 text-xs text-[var(--color-muted-foreground)]">
                        <Clock size={12} aria-hidden />
                        {new Date(s.updated_at).toLocaleDateString()}
                      </span>
                    </Link>
                  ))}
                </Card>
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
