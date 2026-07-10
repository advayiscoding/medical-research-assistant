"""Ingestion pipeline: turn a stored paper/document into searchable chunks.

    source text ── clean+chunk ──> embed ──> ChromaDB (vectors)
                                      └─────> Postgres paper_chunks (text + link)

This is the orchestrator the architecture doc describes. It is the single place
that coordinates the four lower-level services, and it upholds two invariants:

1. Postgres is source of truth. We write the chunk row (with its text) AND the
   Chroma vector, linked by a deterministic chroma_id. If Chroma is ever lost,
   every vector is rebuildable from paper_chunks.
2. Idempotent. Re-ingesting a paper must not duplicate chunks. chroma_id is
   deterministic ("paper:{id}:{index}"), Chroma upserts on it, and we short-
   circuit if the paper already has chunks in Postgres.
"""

import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, Paper, PaperChunk
from app.services import embeddings
from app.services.chunking import chunk_text
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)


async def ingest_paper(db: AsyncSession, paper: Paper, store: VectorStore) -> int:
    """Chunk, embed, and index one paper. Returns the number of chunks created
    (0 if already ingested or no text to index)."""
    if await _already_ingested(db, paper_id=paper.id):
        logger.info("paper %s already ingested, skipping", paper.pmid)
        return 0

    # Title + abstract is the searchable surface for a PubMed record. The title
    # is prepended to every paper's text so a chunk always carries topical
    # context even when the abstract paragraph alone is terse.
    parts = [paper.title]
    if paper.abstract:
        parts.append(paper.abstract)
    source_text = "\n\n".join(parts)

    metadata_base = {
        "source_type": "paper",
        "paper_id": str(paper.id),
        "pmid": paper.pmid,
        "title": paper.title,
        "journal": paper.journal or "",
        "year": paper.publication_date.year if paper.publication_date else 0,
    }
    return await _ingest(
        db, store, source_text, metadata_base, id_prefix=f"paper:{paper.id}",
        paper_id=paper.id, document_id=None,
    )


async def ingest_document(db: AsyncSession, document: Document, text: str,
                          store: VectorStore) -> int:
    """Chunk, embed, and index an uploaded document's extracted text."""
    if await _already_ingested(db, document_id=document.id):
        return 0
    metadata_base = {
        "source_type": "document",
        "document_id": str(document.id),
        "user_id": str(document.user_id),  # enables per-user retrieval filtering
        "title": document.title or document.filename,
        "journal": "",
        "year": 0,
    }
    return await _ingest(
        db, store, text, metadata_base, id_prefix=f"document:{document.id}",
        paper_id=None, document_id=document.id,
    )


async def _ingest(
    db: AsyncSession,
    store: VectorStore,
    source_text: str,
    metadata_base: dict[str, Any],
    id_prefix: str,
    paper_id: Any,
    document_id: Any,
) -> int:
    chunks = chunk_text(source_text)
    if not chunks:
        return 0

    vectors = await embeddings.embed_texts(chunks)

    ids: list[str] = []
    metadatas: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunks):
        ids.append(f"{id_prefix}:{i}")
        metadatas.append({**metadata_base, "chunk_index": i})

    # Chroma client is synchronous/blocking → keep it off the event loop.
    await asyncio.to_thread(store.add, ids, vectors, chunks, metadatas)

    for i, chunk in enumerate(chunks):
        db.add(
            PaperChunk(
                paper_id=paper_id,
                document_id=document_id,
                chunk_index=i,
                text=chunk,
                chroma_id=ids[i],
            )
        )
    await db.flush()
    logger.info("ingested %s -> %d chunks", id_prefix, len(chunks))
    return len(chunks)


async def _already_ingested(
    db: AsyncSession, paper_id: Any = None, document_id: Any = None
) -> bool:
    col = PaperChunk.paper_id if paper_id is not None else PaperChunk.document_id
    val = paper_id if paper_id is not None else document_id
    existing = await db.execute(select(PaperChunk.id).where(col == val).limit(1))
    return existing.first() is not None
