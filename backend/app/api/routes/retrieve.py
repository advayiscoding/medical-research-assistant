"""Semantic retrieval endpoint.

Exposes vector search directly — useful for the frontend "source explorer" and
for verifying retrieval quality independently of the LLM. The RAG endpoint
(Phase 6) uses the same retrieval service internally.
"""

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, VectorStoreDep
from app.schemas.retrieval import RetrieveRequest, RetrieveResponse
from app.services.retrieval import retrieve

router = APIRouter(prefix="/retrieve", tags=["retrieve"])


@router.post("", response_model=RetrieveResponse)
async def retrieve_chunks(
    payload: RetrieveRequest, user: CurrentUserDep, store: VectorStoreDep
) -> RetrieveResponse:
    chunks = await retrieve(payload.query, store, top_k=payload.top_k)
    return RetrieveResponse(query=payload.query, chunks=chunks)
