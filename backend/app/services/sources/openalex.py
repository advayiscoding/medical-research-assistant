"""OpenAlex — a free, comprehensive index of scholarly works with excellent
citation counts and DOIs. https://docs.openalex.org/

Notable quirk: abstracts come as an *inverted index* ({word: [positions]}) for
copyright reasons; we reconstruct the plain text. OpenAlex is our richest source
of `cited_by_count`, which drives the citation half of ranking."""

import logging

from app.services.sources.base import (
    HTTPProvider,
    SourceRecord,
    normalize_doi,
    parse_iso_date,
)

logger = logging.getLogger(__name__)


def _reconstruct_abstract(inverted: dict[str, list[int]] | None) -> str | None:
    if not inverted:
        return None
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted.items():
        for i in idxs:
            positions.append((i, word))
    if not positions:
        return None
    positions.sort()
    return " ".join(word for _, word in positions)


def _strip_pmid(ids: dict) -> str | None:
    pmid_url = ids.get("pmid")
    return pmid_url.rstrip("/").split("/")[-1] if pmid_url else None


class OpenAlexProvider(HTTPProvider):
    name = "openalex"

    async def search(self, query: str, limit: int) -> list[SourceRecord]:
        params = {"search": query, "per_page": limit}
        if self._email:
            params["mailto"] = self._email  # polite pool
        resp = await self._client.get("https://api.openalex.org/works", params=params)
        resp.raise_for_status()
        works = resp.json().get("results", [])

        records: list[SourceRecord] = []
        for rank, w in enumerate(works):
            loc = (w.get("primary_location") or {}).get("source") or {}
            records.append(
                SourceRecord(
                    source=self.name,
                    title=w.get("display_name") or "",
                    abstract=_reconstruct_abstract(w.get("abstract_inverted_index")),
                    authors=[
                        a["author"]["display_name"]
                        for a in w.get("authorships", [])
                        if a.get("author", {}).get("display_name")
                    ],
                    doi=normalize_doi(w["doi"]) if w.get("doi") else None,
                    pmid=_strip_pmid(w.get("ids", {})),
                    external_id=(w.get("id") or "").rstrip("/").split("/")[-1] or None,
                    journal=loc.get("display_name"),
                    publication_date=parse_iso_date(w.get("publication_date")),
                    citation_count=int(w.get("cited_by_count") or 0),
                    url=w.get("doi") or w.get("id"),
                    is_preprint=(w.get("type") == "preprint"),
                    rank=rank,
                )
            )
        return [r for r in records if r.title]
