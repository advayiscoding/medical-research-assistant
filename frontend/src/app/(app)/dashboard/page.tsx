"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Search, MessagesSquare, FileText, ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui";
import type { ChatSession, DocumentItem, SearchHistoryItem } from "@/lib/types";

export default function DashboardPage() {
  const { user } = useAuth();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [searches, setSearches] = useState<SearchHistoryItem[]>([]);

  useEffect(() => {
    // Fire the three summary queries in parallel; ignore individual failures so
    // one empty section doesn't blank the whole dashboard.
    api.listSessions().then(setSessions).catch(() => {});
    api.listDocuments().then(setDocs).catch(() => {});
    api.searchHistory().then(setSearches).catch(() => {});
  }, []);

  const stats = [
    { label: "Chat sessions", value: sessions.length, icon: MessagesSquare },
    { label: "Documents", value: docs.length, icon: FileText },
    { label: "Searches run", value: searches.length, icon: Search },
  ];

  const actions = [
    { href: "/search", title: "Search literature", desc: "Query PubMed and index papers", icon: Search },
    { href: "/chat", title: "Ask a question", desc: "Grounded answers with citations", icon: MessagesSquare },
    { href: "/documents", title: "Upload a PDF", desc: "Make your own papers searchable", icon: FileText },
  ];

  return (
    <div className="flex h-dvh flex-col">
      <PageHeader
        title={`Welcome${user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}`}
        subtitle="Your evidence-grounded research workspace."
      />
      <div className="flex-1 overflow-y-auto px-8 py-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {stats.map(({ label, value, icon: Icon }) => (
            <Card key={label} className="p-5">
              <div className="flex items-center justify-between">
                <span className="text-sm text-[var(--color-muted-foreground)]">{label}</span>
                <Icon size={18} className="text-[var(--color-primary)]" aria-hidden />
              </div>
              <p className="mt-2 font-sans text-3xl font-semibold tabular-nums">{value}</p>
            </Card>
          ))}
        </div>

        <h2 className="mb-3 mt-8 font-sans text-sm font-semibold uppercase tracking-wide text-[var(--color-muted-foreground)]">
          Quick actions
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {actions.map(({ href, title, desc, icon: Icon }) => (
            <Link key={href} href={href}>
              <Card className="group h-full p-5 transition-colors hover:border-[var(--color-primary)]">
                <Icon size={22} className="mb-3 text-[var(--color-primary)]" aria-hidden />
                <div className="flex items-center justify-between">
                  <h3 className="font-sans font-semibold">{title}</h3>
                  <ArrowRight
                    size={16}
                    className="text-[var(--color-muted-foreground)] transition-transform group-hover:translate-x-0.5"
                    aria-hidden
                  />
                </div>
                <p className="mt-1 text-sm text-[var(--color-muted-foreground)]">{desc}</p>
              </Card>
            </Link>
          ))}
        </div>

        {sessions.length > 0 && (
          <>
            <h2 className="mb-3 mt-8 font-sans text-sm font-semibold uppercase tracking-wide text-[var(--color-muted-foreground)]">
              Recent sessions
            </h2>
            <Card className="divide-y divide-[var(--color-border)]">
              {sessions.slice(0, 5).map((s) => (
                <Link
                  key={s.id}
                  href={`/chat/${s.id}`}
                  className="flex items-center justify-between px-5 py-3.5 transition-colors hover:bg-[var(--color-surface-muted)]"
                >
                  <span className="truncate text-sm font-medium">{s.title}</span>
                  <span className="ml-4 shrink-0 text-xs text-[var(--color-muted-foreground)]">
                    {new Date(s.updated_at).toLocaleDateString()}
                  </span>
                </Link>
              ))}
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
