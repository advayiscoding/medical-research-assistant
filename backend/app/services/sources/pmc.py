"""PubMed Central provider — the NCBI full-text archive (Entrez db=pmc).

esearch(db=pmc) gives PMCIDs; efetch(db=pmc) returns JATS XML, from which we
extract the article title and abstract (the abstract is the useful grounding
surface; full body text is large and largely redundant with the abstract for
retrieval). Shares the PubMedClient rate limiter so NCBI's per-IP limit covers
PubMed + PMC together."""

import logging
from xml.etree import ElementTree as ET

from app.services.pubmed import PubMedClient
from app.services.sources.base import SourceRecord

logger = logging.getLogger(__name__)


class PMCProvider:
    name = "pmc"

    def __init__(self, client: PubMedClient) -> None:
        self._client = client

    async def search(self, query: str, limit: int) -> list[SourceRecord]:
        pmcids = await self._client.esearch(query, max_results=limit, db="pmc")
        if not pmcids:
            return []
        xml = await self._client.efetch_pmc_raw(pmcids)
        if not xml:
            return []
        return self._parse(xml)

    @staticmethod
    def _parse(xml_text: str) -> list[SourceRecord]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            logger.warning("PMC efetch XML parse failed")
            return []

        records: list[SourceRecord] = []
        for rank, article in enumerate(root.findall(".//article")):
            meta = article.find(".//front/article-meta")
            if meta is None:
                continue
            title_el = meta.find(".//title-group/article-title")
            title = "".join(title_el.itertext()).strip() if title_el is not None else ""
            if not title:
                continue

            abstract_el = meta.find(".//abstract")
            abstract = None
            if abstract_el is not None:
                abstract = " ".join("".join(abstract_el.itertext()).split()) or None

            pmcid = _article_id(meta, "pmcid") or _article_id(meta, "pmc")
            pmid = _article_id(meta, "pmid")
            doi = _article_id(meta, "doi")
            journal_el = article.find(".//front/journal-meta//journal-title")
            journal = "".join(journal_el.itertext()).strip() if journal_el is not None else None

            records.append(
                SourceRecord(
                    source="pmc",
                    title=title,
                    abstract=abstract,
                    authors=_authors(meta),
                    doi=doi,
                    pmid=pmid,
                    external_id=pmcid,
                    journal=journal,
                    url=(f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid}/"
                         if pmcid else None),
                    rank=rank,
                )
            )
        return records


def _article_id(meta: ET.Element, id_type: str) -> str | None:
    for el in meta.findall(".//article-id"):
        if el.get("pub-id-type") == id_type and el.text:
            return el.text.strip()
    return None


def _authors(meta: ET.Element) -> list[str]:
    names: list[str] = []
    for contrib in meta.findall(".//contrib[@contrib-type='author']"):
        surname = contrib.findtext(".//surname")
        given = contrib.findtext(".//given-names")
        if surname:
            names.append(f"{surname} {given}".strip() if given else surname)
    return names
