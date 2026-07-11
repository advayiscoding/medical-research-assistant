"use client";

// The signature component: renders the sources behind an answer so every claim
// is traceable. Each card leads with its [n] marker (matching the inline
// citations in the answer text) and shows PMID/journal/year + the exact chunk
// that supported the claim, with a link out to PubMed.

import { ExternalLink, FileText, BookOpen } from "lucide-react";
import type { Citation } from "@/lib/types";

export function CitationsPanel({ citations }: { citations: Citation[] }) {
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

            <div className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1 pl-7 text-xs text-[var(--color-muted-foreground)]">
              {isPaper ? (
                <>
                  {chunk.journal && <span>{chunk.journal}</span>}
                  {chunk.year && <span>· {chunk.year}</span>}
                  <a
                    href={`https://pubmed.ncbi.nlm.nih.gov/${chunk.pmid}/`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-[var(--color-primary)] hover:underline"
                  >
                    PMID {chunk.pmid} <ExternalLink size={11} aria-hidden />
                  </a>
                </>
              ) : (
                <span className="inline-flex items-center gap-1">
                  <FileText size={12} aria-hidden /> Uploaded document
                </span>
              )}
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
