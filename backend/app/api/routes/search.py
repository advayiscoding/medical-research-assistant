"""Paper search endpoint.

Thin by design: parse input, call PubMed, persist, shape response. The
"business logic" (idempotent persistence) lives in services/papers.py; the
"how to talk to PubMed" lives in services/pubmed.py. This route just
orchestrates them.

Auth is added in Phase 7b — for now search is open so the pipeline is testable
end-to-end before the auth layer exists.
"""

import logging

from fastapi import APIRouter

from app.api.deps import DbDep, PubMedDep
from app.schemas.paper import PaperRead, SearchRequest, SearchResponse
from app.services.papers import upsert_papers

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=SearchResponse)
async def search_papers(
    payload: SearchRequest,
    pubmed: PubMedDep,
    db: DbDep,
) -> SearchResponse:
    papers = await pubmed.search_and_fetch(payload.query, payload.max_results)
    persisted = await upsert_papers(db, papers)
    await db.commit()

    return SearchResponse(
        query=payload.query,
        count=len(persisted),
        papers=[
            PaperRead(
                id=str(p.id),
                pmid=p.pmid,
                title=p.title,
                authors=p.authors,
                abstract=p.abstract,
                journal=p.journal,
                publication_date=p.publication_date,
            )
            for p in persisted
        ],
    )
