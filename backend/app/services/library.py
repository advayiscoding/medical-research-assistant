"""The corpus-building flow, shared by the search endpoint and chat auto-fetch:

    federated_search (10 sources, parallel, dedup, rank)
        -> upsert_papers (Postgres, idempotent by dedup_key)
        -> ingest_paper  (chunk -> embed -> ChromaDB)

One place so search and chat behave identically and the ordering invariant
(Postgres before Chroma) is never duplicated inconsistently."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Paper
from app.services.federation import federated_search
from app.services.ingestion import ingest_paper
from app.services.papers import upsert_papers
from app.services.sources.base import SourceProvider
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)


async def fetch_store_ingest(
    db: AsyncSession,
    store: VectorStore,
    providers: list[SourceProvider],
    query: str,
    per_source_limit: int = 8,
    final_limit: int = 20,
) -> list[Paper]:
    """Run a federated search and make every returned paper searchable. Returns
    the persisted papers in ranked order."""
    merged = await federated_search(providers, query, per_source_limit, final_limit)
    papers = await upsert_papers(db, merged)
    for paper in papers:
        await ingest_paper(db, paper, store)
    logger.info("fetch_store_ingest %r -> %d papers indexed", query, len(papers))
    return papers
