"""arXiv — preprints in physics, CS, quant-bio, stats. Returns Atom XML (not
JSON), so we parse with ElementTree. https://info.arxiv.org/help/api/

Relevant to medical ML / computational-biology questions; always preprints."""

import logging
from xml.etree import ElementTree as ET

from app.services.sources.base import HTTPProvider, SourceRecord, parse_iso_date

logger = logging.getLogger(__name__)

_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


class ArxivProvider(HTTPProvider):
    name = "arxiv"

    async def search(self, query: str, limit: int) -> list[SourceRecord]:
        params = {
            "search_query": f"all:{query}",
            "max_results": limit,
            "sortBy": "relevance",
        }
        resp = await self._client.get("http://export.arxiv.org/api/query", params=params)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)

        records: list[SourceRecord] = []
        for rank, entry in enumerate(root.findall("atom:entry", _NS)):
            title = (entry.findtext("atom:title", default="", namespaces=_NS) or "").strip()
            if not title:
                continue
            arxiv_url = entry.findtext("atom:id", default="", namespaces=_NS) or ""
            arxiv_id = arxiv_url.rstrip("/").split("/")[-1]
            doi = entry.findtext("arxiv:doi", default=None, namespaces=_NS)
            authors = [
                (a.findtext("atom:name", default="", namespaces=_NS) or "").strip()
                for a in entry.findall("atom:author", _NS)
            ]
            records.append(
                SourceRecord(
                    source=self.name,
                    title=" ".join(title.split()),  # collapse XML whitespace
                    abstract=" ".join(
                        (entry.findtext("atom:summary", default="", namespaces=_NS) or "").split()
                    )
                    or None,
                    authors=[a for a in authors if a],
                    doi=doi,
                    external_id=arxiv_id,
                    journal="arXiv",
                    publication_date=parse_iso_date(
                        (entry.findtext("atom:published", default="", namespaces=_NS) or "")[:10]
                    ),
                    url=arxiv_url,
                    is_preprint=True,
                    rank=rank,
                )
            )
        return records
