"""Federated paper search endpoint.

Thin by design: parse input, run the federated search (10 sources in parallel,
deduplicated and ranked), persist + index, shape the response. The federation,
persistence, and ingestion live in services; this route just orchestrates and
records search history.
"""

import logging

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, DbDep, SourceProvidersDep, VectorStoreDep
from app.models import SearchHistory
from app.schemas.paper import PaperRead, SearchRequest, SearchResponse
from app.services.library import fetch_store_ingest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=SearchResponse)
async def search_papers(
    payload: SearchRequest,
    user: CurrentUserDep,
    providers: SourceProvidersDep,
    db: DbDep,
    store: VectorStoreDep,
) -> SearchResponse:
    # Federate across all sources, dedup/rank, persist, and index so results are
    # immediately answerable in Chat. Idempotent by dedup_key, so re-searching a
    # known topic re-indexes nothing.
    papers = await fetch_store_ingest(
        db, store, providers, payload.query, final_limit=payload.max_results
    )

    db.add(SearchHistory(user_id=user.id, query=payload.query, result_count=len(papers)))
    await db.commit()

    return SearchResponse(
        query=payload.query,
        count=len(papers),
        papers=[
            PaperRead(
                id=str(p.id),
                pmid=p.pmid,
                doi=p.doi,
                title=p.title,
                authors=p.authors,
                abstract=p.abstract,
                journal=p.journal,
                publication_date=p.publication_date,
                source=p.source,
                sources=p.sources or [p.source],
                citation_count=p.citation_count,
                url=p.url,
                is_preprint=p.is_preprint,
            )
            for p in papers
        ],
    )
