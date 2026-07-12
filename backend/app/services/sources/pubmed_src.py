"""PubMed provider — adapts the existing PubMedClient (E-utilities esearch +
efetch, with rate limiting and the natural-language relax fallback) to the
federated SourceProvider interface. No new HTTP logic; just a shape translation
from PubMedPaper to SourceRecord."""

import logging

from app.services.pubmed import PubMedClient
from app.services.sources.base import SourceRecord

logger = logging.getLogger(__name__)


class PubMedProvider:
    name = "pubmed"

    def __init__(self, client: PubMedClient) -> None:
        self._client = client

    async def search(self, query: str, limit: int) -> list[SourceRecord]:
        papers = await self._client.search_and_fetch(query, max_results=limit)
        return [
            SourceRecord(
                source=self.name,
                title=p.title,
                abstract=p.abstract,
                authors=p.authors,
                pmid=p.pmid,
                external_id=p.pmid,
                journal=p.journal,
                publication_date=p.publication_date,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{p.pmid}/",
                rank=rank,
            )
            for rank, p in enumerate(papers)
        ]
