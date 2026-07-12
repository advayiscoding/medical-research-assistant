"""Europe PMC — aggregates PubMed, PMC, Agricola, patents, and preprints.
https://europepmc.org/RestfulWebService

`resultType=core` returns full abstracts and citation counts. This module also
backs the bioRxiv and medRxiv providers: those preprint servers have no usable
keyword-search API of their own, but Europe PMC indexes them and lets us filter
by `PUBLISHER:"bioRxiv"` / `PUBLISHER:"medRxiv"` (verified: 91 and 213 hits for a
diabetes query). So bioRxiv/medRxiv are logically distinct sources retrieved
through Europe PMC's index — the standard, reliable route."""

import logging

from app.services.sources.base import HTTPProvider, SourceRecord, normalize_doi, year_to_date

logger = logging.getLogger(__name__)

_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


async def _query_epmc(
    client, query: str, limit: int, source_name: str
) -> list[SourceRecord]:
    params = {"query": query, "format": "json", "pageSize": limit, "resultType": "core"}
    resp = await client.get(_BASE, params=params)
    resp.raise_for_status()
    results = resp.json().get("resultList", {}).get("result", [])

    records: list[SourceRecord] = []
    for rank, r in enumerate(results):
        journal = (r.get("journalInfo") or {}).get("journal", {}).get("title")
        if not journal:
            journal = (r.get("bookOrReportDetails") or {}).get("publisher")
        doi = r.get("doi")
        pmid = r.get("pmid")
        records.append(
            SourceRecord(
                source=source_name,
                title=r.get("title") or "",
                abstract=r.get("abstractText"),
                authors=_split_authors(r.get("authorString")),
                doi=normalize_doi(doi) if doi else None,
                pmid=pmid,
                external_id=r.get("id"),
                journal=journal,
                publication_date=year_to_date(r.get("pubYear")),
                citation_count=int(r.get("citedByCount") or 0),
                url=(f"https://doi.org/{normalize_doi(doi)}" if doi
                     else f"https://europepmc.org/article/{r.get('source')}/{r.get('id')}"),
                is_preprint=(r.get("source") == "PPR"),
                rank=rank,
            )
        )
    return [r for r in records if r.title]


def _split_authors(author_string: str | None) -> list[str]:
    if not author_string:
        return []
    # "Smith J, Doe A." -> ["Smith J", "Doe A"]
    return [a.strip().rstrip(".") for a in author_string.split(",") if a.strip()]


class EuropePMCProvider(HTTPProvider):
    name = "europepmc"

    async def search(self, query: str, limit: int) -> list[SourceRecord]:
        return await _query_epmc(self._client, query, limit, self.name)


class BioRxivProvider(HTTPProvider):
    name = "biorxiv"

    async def search(self, query: str, limit: int) -> list[SourceRecord]:
        q = f'{query} AND SRC:PPR AND PUBLISHER:"bioRxiv"'
        return await _query_epmc(self._client, q, limit, self.name)


class MedRxivProvider(HTTPProvider):
    name = "medrxiv"

    async def search(self, query: str, limit: int) -> list[SourceRecord]:
        q = f'{query} AND SRC:PPR AND PUBLISHER:"medRxiv"'
        return await _query_epmc(self._client, q, limit, self.name)
