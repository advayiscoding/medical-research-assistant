"""PubMed / NCBI E-utilities client.

This is the ONLY module in the codebase that knows how to talk to PubMed
(ARCHITECTURE.md §2). It exposes two operations the app needs:

    esearch(query)  -> list of PMIDs      (which papers match?)
    efetch(pmids)   -> list of PubMedPaper (get their metadata + abstracts)

Design decisions
----------------
* Async httpx: search is on the request path; blocking the event loop on a
  network round-trip would stall every other concurrent request.
* Rate limiting: NCBI allows 3 req/s (10 with an API key). We enforce this
  with a small async throttle so we are a well-behaved API citizen and never
  get a 429. The limit is a hard NCBI rule, not a nicety.
* XML, not JSON: efetch returns richer, more reliable data as XML
  (`retmode=xml`). We parse with the stdlib ElementTree — no extra dependency,
  and PubMed's schema is stable.
* Structured abstracts (Background/Methods/Results/Conclusions) are flattened
  to "LABEL: text" blocks so downstream chunking sees clean prose.
"""

import asyncio
import logging
import re
import time
from datetime import date
from xml.etree import ElementTree as ET

import httpx

from app.core.config import Settings
from app.schemas.paper import PubMedPaper

logger = logging.getLogger(__name__)

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# Filler and question words that make PubMed (which ANDs every term literally)
# return nothing for natural-language queries like "latest cures for X". We
# strip ONLY non-clinical filler — words like "treatment", "therapy", "risk",
# "diagnosis" are kept because they are legitimate, high-signal PubMed terms.
_QUERY_STOPWORDS = frozenset({
    "a", "an", "the", "of", "for", "in", "on", "to", "and", "or", "with", "about",
    "what", "whats", "which", "who", "how", "is", "are", "do", "does", "can", "could",
    "i", "my", "me", "we", "you", "there", "any",
    "latest", "recent", "recently", "newest", "new", "current", "currently", "modern",
    "best", "most", "effective", "good", "better", "promising", "emerging",
    "cure", "cures", "cured",  # medical literature indexes "therapy"/"treatment", not "cure"
})

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def relax_query(query: str) -> str:
    """Strip filler/question words from a natural-language query, leaving the
    clinical keywords PubMed actually matches on. Pure function — no network —
    so it is cheap to unit-test. Returns "" if nothing survives (all stopwords),
    in which case the caller keeps the original query rather than searching for
    nothing."""
    kept = [
        w for w in re.findall(r"[A-Za-z0-9'-]+", query)
        if w.lower() not in _QUERY_STOPWORDS
    ]
    return " ".join(kept)


class _RateLimiter:
    """Token-bucket-ish throttle: guarantees a minimum interval between calls.

    A lock serializes access so concurrent requests queue instead of all
    firing at once. Simple and correct for a single process; a distributed
    deployment would move this to Redis, but Container Apps replicas each
    staying under the limit is fine because NCBI limits per-IP and we sit
    behind one egress.
    """

    def __init__(self, per_second: float) -> None:
        self._min_interval = 1.0 / per_second
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            wait = self._min_interval - (time.monotonic() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


class PubMedClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(timeout=20.0)
        self._owns_client = client is None
        rate = 10.0 if settings.pubmed_api_key else 3.0
        self._limiter = _RateLimiter(rate)

    async def __aenter__(self) -> "PubMedClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _common_params(self, db: str = "pubmed") -> dict[str, str]:
        params = {"db": db, "tool": "medresearch-ai"}
        if self._settings.pubmed_api_key:
            params["api_key"] = self._settings.pubmed_api_key
        if self._settings.pubmed_email:
            params["email"] = self._settings.pubmed_email
        return params

    async def esearch(self, query: str, max_results: int = 10, db: str = "pubmed") -> list[str]:
        """Return record UIDs matching an NCBI query, most relevant first. `db`
        selects the Entrez database — "pubmed" for abstracts, "pmc" for the full-
        text archive. Both share this client's rate limiter, so the two NCBI
        sources never exceed the shared per-IP limit."""
        await self._limiter.acquire()
        params = {
            **self._common_params(db),
            "term": query,
            "retmax": str(max_results),
            "retmode": "json",
            "sort": "relevance",
        }
        resp = await self._client.get(f"{EUTILS_BASE}/esearch.fcgi", params=params)
        resp.raise_for_status()
        data = resp.json()
        uids: list[str] = data.get("esearchresult", {}).get("idlist", [])
        logger.info("esearch[%s] %r -> %d ids", db, query, len(uids))
        return uids

    async def efetch_pmc_raw(self, pmcids: list[str]) -> str:
        """Fetch raw JATS XML for PMC articles (full text). Parsing is left to the
        PMC provider, which extracts title + abstract."""
        if not pmcids:
            return ""
        await self._limiter.acquire()
        params = {**self._common_params("pmc"), "id": ",".join(pmcids), "retmode": "xml"}
        resp = await self._client.get(f"{EUTILS_BASE}/efetch.fcgi", params=params)
        resp.raise_for_status()
        return resp.text

    async def efetch(self, pmids: list[str]) -> list[PubMedPaper]:
        """Fetch metadata + abstracts for a batch of PMIDs in one call."""
        if not pmids:
            return []
        await self._limiter.acquire()
        params = {
            **self._common_params(),
            "id": ",".join(pmids),
            "retmode": "xml",
        }
        resp = await self._client.get(f"{EUTILS_BASE}/efetch.fcgi", params=params)
        resp.raise_for_status()
        return self._parse_articles(resp.text)

    async def search_and_fetch(self, query: str, max_results: int = 10) -> list[PubMedPaper]:
        """Convenience: the esearch -> efetch chain the app almost always wants.

        If the raw query finds nothing, retry once with filler words removed.
        PubMed matches literally and ANDs every term, so a natural-language
        question ("latest cures for schizophrenia") often yields zero hits while
        its keyword core ("schizophrenia") returns plenty. The fallback makes the
        product forgiving of how real users phrase things, without silently
        broadening a query that already worked.
        """
        pmids = await self.esearch(query, max_results)
        if not pmids:
            relaxed = relax_query(query)
            if relaxed and relaxed.lower() != query.lower():
                logger.info("no hits for %r; retrying relaxed query %r", query, relaxed)
                pmids = await self.esearch(relaxed, max_results)
        return await self.efetch(pmids)

    # --- XML parsing -----------------------------------------------------

    @classmethod
    def _parse_articles(cls, xml_text: str) -> list[PubMedPaper]:
        root = ET.fromstring(xml_text)
        papers: list[PubMedPaper] = []
        for art in root.findall(".//PubmedArticle"):
            paper = cls._parse_one(art)
            if paper is not None:
                papers.append(paper)
        return papers

    @classmethod
    def _parse_one(cls, art: ET.Element) -> PubMedPaper | None:
        pmid_el = art.find(".//PMID")
        if pmid_el is None or not pmid_el.text:
            return None
        pmid = pmid_el.text.strip()

        title = "".join(art.find(".//ArticleTitle").itertext()).strip() if art.find(
            ".//ArticleTitle"
        ) is not None else ""
        if not title:
            # Dead/unpopulated record (see fetch-and-resolve.md). Skip it.
            return None

        authors: list[str] = []
        for author in art.findall(".//Author"):
            last = author.findtext("LastName")
            initials = author.findtext("Initials")
            collective = author.findtext("CollectiveName")
            if last:
                authors.append(f"{last} {initials}".strip() if initials else last)
            elif collective:
                authors.append(collective)

        journal = art.findtext(".//Journal/Title")
        abstract = cls._parse_abstract(art)
        pub_date = cls._parse_date(art)

        return PubMedPaper(
            pmid=pmid,
            title=title,
            authors=authors,
            abstract=abstract,
            journal=journal,
            publication_date=pub_date,
        )

    @staticmethod
    def _parse_abstract(art: ET.Element) -> str | None:
        """Flatten (possibly structured) abstract text into a single string."""
        parts: list[str] = []
        for node in art.findall(".//Abstract/AbstractText"):
            text = "".join(node.itertext()).strip()
            if not text:
                continue
            label = node.get("Label")
            parts.append(f"{label}: {text}" if label else text)
        return "\n".join(parts) if parts else None

    @classmethod
    def _parse_date(cls, art: ET.Element) -> date | None:
        """Best-effort publication date. PubMed dates are notoriously ragged:
        some records have only a year, some a MedlineDate string like
        '2023 Spring'. We extract year+month+day where present, default month
        and day to 1, and return None if we can't even find a year."""
        pd = art.find(".//Journal/JournalIssue/PubDate")
        if pd is None:
            return None
        year_text = pd.findtext("Year")
        if not year_text:
            medline = pd.findtext("MedlineDate") or ""
            year_text = medline[:4] if medline[:4].isdigit() else None
        if not year_text or not year_text.isdigit():
            return None
        year = int(year_text)

        month_text = (pd.findtext("Month") or "1").strip()
        month = _MONTHS.get(month_text[:3].lower(), None)
        if month is None:
            month = int(month_text) if month_text.isdigit() else 1

        day_text = (pd.findtext("Day") or "1").strip()
        day = int(day_text) if day_text.isdigit() else 1
        try:
            return date(year, month, day)
        except ValueError:
            return date(year, 1, 1)
