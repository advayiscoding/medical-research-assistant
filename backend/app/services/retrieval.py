"""Retrieval strategy — the layer between raw vector search and RAG.

VectorStore.query() is a dumb nearest-neighbor lookup. Real retrieval quality
comes from what you do around it. This service implements four strategy pieces,
each with a concrete purpose:

1. Query/document symmetry
   The query is embedded with the exact same model + normalization used at
   ingestion (embeddings.embed_query). Mismatched embedders make distances
   meaningless — the single most common RAG bug.

2. Over-fetch, then filter
   Thresholding and per-paper capping SHRINK the candidate set, so we ask Chroma
   for more than we need (top_k * OVERFETCH) and trim down to top_k afterwards.
   Fetching exactly top_k and then dropping some would under-deliver.

3. Relevance floor (hallucination control #1)
   Chunks below MIN_SCORE are discarded. If nothing clears the floor we return
   [], and the RAG layer answers "insufficient evidence" instead of grounding on
   noise. A vector search ALWAYS returns its k nearest neighbors, even for an
   off-topic question — the floor is what turns "nearest" into "relevant".

4. Per-paper diversity
   At most MAX_PER_SOURCE chunks from any one paper survive. Without this, a
   single long, on-topic paper can fill the whole context window and starve the
   answer of corroborating sources — bad for citation breadth and for balance.

Ranking is by similarity score throughout (Chroma returns nearest-first; we
preserve that order through filtering). A cross-encoder re-ranker would improve
precision further and is the natural next upgrade; it slots in right here behind
the same interface.
"""

import logging
from typing import Any

from app.schemas.retrieval import RetrievedChunk
from app.services import embeddings
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)

MIN_SCORE = 0.25          # cosine-similarity floor; below this = not relevant
OVERFETCH = 3             # fetch top_k * OVERFETCH candidates before trimming
MAX_PER_SOURCE = 2        # cap chunks per paper for evidence diversity


async def retrieve(
    query: str,
    store: VectorStore,
    top_k: int = 5,
    where: dict[str, Any] | None = None,
    min_score: float = MIN_SCORE,
) -> list[RetrievedChunk]:
    """Return up to top_k relevant, diverse chunks for a query, best first."""
    qvec = await embeddings.embed_query(query)
    raw = store.query(qvec, top_k=top_k * OVERFETCH, where=where)

    kept: list[RetrievedChunk] = []
    per_source: dict[str, int] = {}
    for hit in raw:
        if hit.score < min_score:
            continue  # relevance floor
        meta = hit.metadata
        source_key = meta.get("pmid") or meta.get("document_id") or hit.chroma_id
        if per_source.get(source_key, 0) >= MAX_PER_SOURCE:
            continue  # diversity cap
        per_source[source_key] = per_source.get(source_key, 0) + 1

        kept.append(
            RetrievedChunk(
                chunk_id=None,
                chroma_id=hit.chroma_id,
                text=hit.text,
                score=round(hit.score, 4),
                source_type=meta.get("source_type", "paper"),
                pmid=meta.get("pmid") or None,
                title=meta.get("title", ""),
                journal=meta.get("journal", ""),
                year=meta.get("year") or None,
            )
        )
        if len(kept) >= top_k:
            break

    logger.info("retrieve %r -> %d/%d chunks kept", query, len(kept), len(raw))
    return kept
