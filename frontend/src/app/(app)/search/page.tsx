"use client";

import { useState } from "react";
import { Search as SearchIcon, ExternalLink, Users, Quote } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { Button, Input, Card, Spinner } from "@/components/ui";
import { sourceColor, sourceLabel } from "@/lib/sources";
import type { Paper } from "@/lib/types";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [papers, setPapers] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  async function onSearch(e: React.FormEvent) {
    e.preventDefault();
    if (query.trim().length < 2) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.search(query, 10);
      setPapers(res.papers);
      setSearched(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-dvh flex-col">
      <PageHeader
        title="Search literature"
        subtitle="Federated across 10 sources (PubMed, OpenAlex, Europe PMC, Crossref, arXiv, bioRxiv, medRxiv, ClinicalTrials.gov, PMC, openFDA). Results are deduplicated, ranked, and indexed for Chat."
      />
      <div className="flex-1 overflow-y-auto px-8 py-6">
        <form onSubmit={onSearch} className="mb-6 flex gap-2">
          <div className="relative flex-1">
            <SearchIcon
              size={18}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-muted-foreground)]"
              aria-hidden
            />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. latest treatments for Alzheimer's disease"
              className="pl-10"
              aria-label="Search query"
            />
          </div>
          <Button type="submit" disabled={loading}>
            {loading ? "Searching…" : "Search"}
          </Button>
        </form>

        {loading && <Spinner label="Querying PubMed and indexing results…" />}
        {error && (
          <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        )}

        {!loading && searched && papers.length === 0 && (
          <p className="text-sm text-[var(--color-muted-foreground)]">
            No papers found. Try broader terms.
          </p>
        )}

        <div className="space-y-3">
          {papers.map((p) => (
            <Card key={p.id} className="p-5">
              <div className="mb-2 flex flex-wrap items-center gap-1">
                {(p.sources.length ? p.sources : [p.source]).map(
                  (s) =>
                    s && (
                      <span
                        key={s}
                        className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${sourceColor(s)}`}
                      >
                        {sourceLabel(s)}
                      </span>
                    ),
                )}
                {p.is_preprint && (
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-800">
                    Preprint
                  </span>
                )}
                {p.citation_count > 0 && (
                  <span className="inline-flex items-center gap-0.5 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600">
                    <Quote size={9} aria-hidden /> {p.citation_count.toLocaleString()} cites
                  </span>
                )}
              </div>
              <div className="flex items-start justify-between gap-4">
                <h3 className="font-sans font-semibold leading-snug">{p.title}</h3>
                {(p.url || p.pmid) && (
                  <a
                    href={p.url ?? `https://pubmed.ncbi.nlm.nih.gov/${p.pmid}/`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex shrink-0 items-center gap-1 text-xs text-[var(--color-primary)] hover:underline"
                  >
                    View <ExternalLink size={11} aria-hidden />
                  </a>
                )}
              </div>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--color-muted-foreground)]">
                {p.journal && <span>{p.journal}</span>}
                {p.publication_date && <span>· {new Date(p.publication_date).getFullYear()}</span>}
                {p.authors.length > 0 && (
                  <span className="inline-flex items-center gap-1">
                    <Users size={12} aria-hidden />
                    {p.authors.slice(0, 3).join(", ")}
                    {p.authors.length > 3 && " et al."}
                  </span>
                )}
              </div>
              {p.abstract && (
                <p className="mt-3 text-sm leading-relaxed text-[var(--color-muted-foreground)] line-clamp-4">
                  {p.abstract}
                </p>
              )}
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
