// Display metadata for the ten federated sources: a human label and a color,
// so provenance badges read consistently across the search and citation UIs.

export const SOURCE_LABELS: Record<string, string> = {
  pubmed: "PubMed",
  pmc: "PubMed Central",
  openalex: "OpenAlex",
  clinicaltrials: "ClinicalTrials.gov",
  europepmc: "Europe PMC",
  crossref: "Crossref",
  arxiv: "arXiv",
  biorxiv: "bioRxiv",
  medrxiv: "medRxiv",
  fda: "openFDA",
};

// Tailwind classes per source (light bg + readable text, WCAG-friendly).
export const SOURCE_COLORS: Record<string, string> = {
  pubmed: "bg-cyan-100 text-cyan-800",
  pmc: "bg-teal-100 text-teal-800",
  openalex: "bg-indigo-100 text-indigo-800",
  clinicaltrials: "bg-emerald-100 text-emerald-800",
  europepmc: "bg-sky-100 text-sky-800",
  crossref: "bg-amber-100 text-amber-800",
  arxiv: "bg-red-100 text-red-800",
  biorxiv: "bg-lime-100 text-lime-800",
  medrxiv: "bg-orange-100 text-orange-800",
  fda: "bg-violet-100 text-violet-800",
};

export function sourceLabel(name: string): string {
  return SOURCE_LABELS[name] ?? name;
}

export function sourceColor(name: string): string {
  return SOURCE_COLORS[name] ?? "bg-slate-100 text-slate-700";
}
