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

from app.api.deps import CurrentUserDep, DbDep, PubMedDep, VectorStoreDep
from app.models import SearchHistory
from app.schemas.paper import PaperRead, SearchRequest, SearchResponse
from app.services.ingestion import ingest_paper
from app.services.papers import upsert_papers

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=SearchResponse)
async def search_papers(
    payload: SearchRequest,
    user: CurrentUserDep,
    pubmed: PubMedDep,
    db: DbDep,
    store: VectorStoreDep,
) -> SearchResponse:
    papers = await pubmed.search_and_fetch(payload.query, payload.max_results)
    persisted = await upsert_papers(db, papers)

    # Ingest each paper so it is immediately semantically searchable. This is
    # idempotent (see ingestion.py), so re-searching a known topic re-indexes
    # nothing. For a portfolio-scale corpus doing this inline is fine; at larger
    # scale this would move to a background task/queue so search stays snappy.
    for paper in persisted:
        await ingest_paper(db, paper, store)

    db.add(SearchHistory(user_id=user.id, query=payload.query, result_count=len(persisted)))
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
