"""Crossref — the DOI registration agency for most journals. Great for DOIs and
`is-referenced-by-count` (citation counts). https://api.crossref.org/

Abstracts, when present, are JATS-XML-tagged (<jats:p>…); we strip the tags."""

import logging
import re

from app.services.sources.base import HTTPProvider, SourceRecord, normalize_doi

logger = logging.getLogger(__name__)

_JATS_TAG = re.compile(r"<[^>]+>")


def _clean_abstract(raw: str | None) -> str | None:
    if not raw:
        return None
    text = _JATS_TAG.sub(" ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    # Drop a leading "Abstract" label some publishers include.
    return re.sub(r"^abstract\s*", "", text, flags=re.IGNORECASE) or None


def _date_from_parts(obj: dict | None):
    from datetime import date

    if not obj:
        return None
    parts = (obj.get("date-parts") or [[None]])[0]
    if not parts or parts[0] is None:
        return None
    y = parts[0]
    m = parts[1] if len(parts) > 1 else 1
    d = parts[2] if len(parts) > 2 else 1
    try:
        return date(int(y), int(m), int(d))
    except (ValueError, TypeError):
        return None


class CrossrefProvider(HTTPProvider):
    name = "crossref"

    async def search(self, query: str, limit: int) -> list[SourceRecord]:
        params = {"query": query, "rows": limit}
        if self._email:
            params["mailto"] = self._email  # polite pool
        resp = await self._client.get("https://api.crossref.org/works", params=params)
        resp.raise_for_status()
        items = resp.json().get("message", {}).get("items", [])

        records: list[SourceRecord] = []
        for rank, it in enumerate(items):
            title_list = it.get("title") or []
            title = title_list[0] if title_list else ""
            container = it.get("container-title") or []
            authors = [
                " ".join(filter(None, [a.get("given"), a.get("family")])).strip()
                for a in it.get("author", [])
            ]
            doi = it.get("DOI")
            is_preprint = it.get("type") == "posted-content"
            records.append(
                SourceRecord(
                    source=self.name,
                    title=title,
                    abstract=_clean_abstract(it.get("abstract")),
                    authors=[a for a in authors if a],
                    doi=normalize_doi(doi) if doi else None,
                    external_id=doi,
                    journal=container[0] if container else None,
                    publication_date=_date_from_parts(
                        it.get("issued") or it.get("published")
                    ),
                    citation_count=int(it.get("is-referenced-by-count") or 0),
                    url=it.get("URL") or (f"https://doi.org/{normalize_doi(doi)}" if doi else None),
                    is_preprint=is_preprint,
                    rank=rank,
                )
            )
        return [r for r in records if r.title]
