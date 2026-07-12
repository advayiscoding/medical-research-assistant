"use client";

// The signature component: renders the sources behind an answer so every claim
// is traceable. Each card leads with its [n] marker (matching the inline
// citations in the answer text) and shows PMID/journal/year + the exact chunk
// that supported the claim, with a link out to PubMed.

import { ExternalLink, FileText, BookOpen, SearchX, Quote } from "lucide-react";
import type { Citation } from "@/lib/types";
import { sourceColor, sourceLabel } from "@/lib/sources";

export function CitationsPanel({
  citations,
  insufficient = false,
}: {
  citations: Citation[];
  insufficient?: boolean;
}) {
  // Refusal: no source list, because the retrieved chunks did not actually
  // support an answer. Showing them here would imply otherwise.
  if (insufficient) {
    return (
      <div className="p-6 text-sm text-[var(--color-muted-foreground)]">
        <SearchX size={20} className="mb-2 opacity-70" aria-hidden />
        <p className="font-medium text-[var(--color-foreground)]">No supporting evidence</p>
        <p className="mt-1">
          The indexed literature doesn&rsquo;t cover this question. Try the{" "}
          <span className="font-medium">Search</span> page to add relevant papers,
          then ask again.
        </p>
      </div>
    );
  }

  if (citations.length === 0) {
    return (
      <div className="p-6 text-sm text-[var(--color-muted-foreground)]">
        <BookOpen size={20} className="mb-2 opacity-60" aria-hidden />
        Sources for the answer will appear here. Every claim is grounded in
        retrieved literature.
      </div>
    );
  }

  return (
    <div className="space-y-3 p-4">
      <h2 className="px-1 font-sans text-sm font-semibold uppercase tracking-wide text-[var(--color-muted-foreground)]">
        Sources ({citations.length})
      </h2>
      {citations.map((c) => {
        const { chunk } = c;
        const isPaper = chunk.source_type === "paper" && chunk.pmid;
        return (
          <div
            key={`${c.marker}-${chunk.chroma_id}`}
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3"
          >
            <div className="mb-1.5 flex items-start gap-2">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded bg-[var(--color-primary)] text-xs font-semibold text-white">
                {c.marker}
              </span>
              <p className="text-sm font-medium leading-snug">{chunk.title || "Untitled source"}</p>
            </div>

            {/* Source provenance: which federated API(s) returned this paper. */}
            <div className="mb-1.5 flex flex-wrap items-center gap-1 pl-7">
              {chunk.source_type === "document" ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-700">
                  <FileText size={10} aria-hidden /> Uploaded document
                </span>
              ) : (
                (chunk.sources.length ? chunk.sources : [chunk.source]).map(
                  (s) =>
                    s && (
                      <span
                        key={s}
                        className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${sourceColor(s)}`}
                      >
                        {sourceLabel(s)}
                      </span>
                    ),
                )
              )}
              {chunk.citation_count > 0 && (
                <span className="inline-flex items-center gap-0.5 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600">
                  <Quote size={9} aria-hidden /> {chunk.citation_count.toLocaleString()} cites
                </span>
              )}
            </div>

            <div className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1 pl-7 text-xs text-[var(--color-muted-foreground)]">
              {isPaper ? (
                <>
                  {chunk.journal && <span>{chunk.journal}</span>}
                  {chunk.year ? <span>· {chunk.year}</span> : null}
                  {(chunk.url || chunk.pmid) && (
                    <a
                      href={
                        chunk.url ??
                        `https://pubmed.ncbi.nlm.nih.gov/${chunk.pmid}/`
                      }
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[var(--color-primary)] hover:underline"
                    >
                      {chunk.pmid ? `PMID ${chunk.pmid}` : "View source"}{" "}
                      <ExternalLink size={11} aria-hidden />
                    </a>
                  )}
                </>
              ) : null}
            </div>

            <p className="pl-7 text-xs leading-relaxed text-[var(--color-muted-foreground)] line-clamp-4">
              &ldquo;{chunk.text}&rdquo;
            </p>
          </div>
        );
      })}
    </div>
  );
}
