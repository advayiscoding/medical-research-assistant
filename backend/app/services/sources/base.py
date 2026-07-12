"""Shared building blocks for the federated source providers.

Every provider — PubMed, OpenAlex, Crossref, arXiv, ClinicalTrials.gov, Europe
PMC, PMC, bioRxiv, medRxiv, openFDA — normalizes its API's response into the
same `SourceRecord` DTO, so the federation layer above treats all ten
identically. The only thing that differs per source is how you *get* the data;
the shape you hand back is uniform. That uniformity is what makes dedup, merge,
and ranking source-agnostic.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol, runtime_checkable

import httpx


@dataclass
class SourceRecord:
    """One normalized scholarly record, before persistence. Ranking metadata
    (rank within its source, relevance) is attached by the federation layer."""

    source: str  # provider name: "pubmed", "openalex", …
    title: str
    abstract: str | None = None
    authors: list[str] = field(default_factory=list)
    doi: str | None = None
    pmid: str | None = None
    external_id: str | None = None  # arXiv id, NCT number, FDA label id, PMCID…
    journal: str | None = None
    publication_date: date | None = None
    citation_count: int = 0
    url: str | None = None
    is_preprint: bool = False
    # Set by the provider: 0-based position in that source's own result list.
    # The federation layer fuses these ranks across sources (RRF).
    rank: int = 0

    def dedup_key(self) -> str:
        """Canonical cross-source identity. Priority: DOI (globally unique across
        publishers) > PMID > source-specific id > title hash. Two records from
        different APIs describing the same paper collapse iff they share a key —
        which is why DOI is preferred (arXiv, Crossref, OpenAlex, Europe PMC all
        expose it)."""
        if self.doi:
            return f"doi:{normalize_doi(self.doi)}"
        if self.pmid:
            return f"pmid:{self.pmid}"
        if self.external_id:
            return f"{self.source}:{self.external_id}"
        return f"title:{_title_hash(self.title)}"


def normalize_doi(doi: str) -> str:
    """Strip URL/prefix noise and lowercase so the same DOI from different APIs
    (some return bare, some as https://doi.org/…) compares equal."""
    doi = doi.strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    return doi.removeprefix("doi:")


def parse_iso_date(s: str | None) -> date | None:
    """Parse a 'YYYY-MM-DD' (or 'YYYY/MM/DD', or bare 'YYYY') string leniently."""
    if not s:
        return None
    parts = re.split(r"[-/]", s.strip())
    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 and parts[1] else 1
        day = int(parts[2]) if len(parts) > 2 and parts[2] else 1
        return date(year, month, day)
    except (ValueError, IndexError):
        return None


def year_to_date(year: object) -> date | None:
    """Some sources give only a publication year; anchor it to Jan 1."""
    try:
        return date(int(str(year)), 1, 1)
    except (ValueError, TypeError):
        return None


def _title_hash(title: str) -> str:
    # Last-resort dedup for records with no identifier: normalize aggressively
    # (lowercase, alphanumerics only) so punctuation/spacing differences don't
    # defeat the match, then hash for a compact stable key.
    norm = re.sub(r"[^a-z0-9]+", "", title.lower())
    return hashlib.sha1(norm.encode()).hexdigest()[:20]


@runtime_checkable
class SourceProvider(Protocol):
    """What the federation layer needs from every source. Implementations hold a
    shared httpx client and any config (polite-pool email) and translate one
    keyword query into normalized records, in the source's own relevance order."""

    name: str

    async def search(self, query: str, limit: int) -> list[SourceRecord]: ...


class HTTPProvider:
    """Base for HTTP-backed providers: holds the shared async client and the
    contact email used for the 'polite pool' several APIs reward with higher
    rate limits (OpenAlex, Crossref, NCBI)."""

    name: str = "http"

    def __init__(self, client: httpx.AsyncClient, email: str = "") -> None:
        self._client = client
        self._email = email
