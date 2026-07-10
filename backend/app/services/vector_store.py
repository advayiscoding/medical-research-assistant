"""ChromaDB access — the ONLY module that imports chromadb (ARCHITECTURE.md §2).

Everything else talks to this interface: add(), query(), delete(). When we
swap ChromaDB for pgvector or Pinecone, this file changes and nothing else does.

Design decisions
----------------
* Two client modes from one config:
    - Embedded PersistentClient (local dev): Chroma runs in-process, persisting
      to a directory. Zero infra to stand up.
    - HttpClient (docker/cloud): Chroma runs as its own service. Same interface.
  The switch is a single env var (CHROMA_HOST), so dev and prod share code.

* Collection name is versioned by embedding model. Vectors from different models
  live in different geometric spaces; mixing them silently corrupts search.
  Encoding the model in the collection name makes that impossible.

* Cosine distance (hnsw:space = cosine). Text embeddings are compared by angle,
  not magnitude; with our L2-normalized vectors this is the correct metric.

* Metadata travels with every vector. We store pmid/document title/journal/year
  on each vector so a search result is self-describing — the RAG layer can build
  a citation without a second DB round-trip per hit.

* We pass precomputed embeddings (embedding_function=None). Chroma can embed for
  us, but we own embedding in embeddings.py so ingestion and query use exactly
  the same model and normalization. One source of truth for vectors.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class VectorHit:
    """One search result: the chunk's Chroma id, its stored text/metadata, and
    a normalized similarity score in [0, 1] (1 = identical)."""

    chroma_id: str
    text: str
    metadata: dict[str, Any]
    score: float


def _collection_name(model_name: str) -> str:
    # e.g. "sentence-transformers/all-MiniLM-L6-v2" -> "chunks__all_minilm_l6_v2"
    slug = re.sub(r"[^a-z0-9]+", "_", model_name.split("/")[-1].lower()).strip("_")
    return f"chunks__{slug}"


class VectorStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        if settings.chroma_host:
            self._client = chromadb.HttpClient(
                host=settings.chroma_host,
                port=settings.chroma_port,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        else:
            self._client = chromadb.PersistentClient(
                path=settings.chroma_persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        self._collection = self._client.get_or_create_collection(
            name=_collection_name(settings.embedding_model),
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,  # we always supply our own vectors
        )

    def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Upsert vectors. Chroma's upsert is idempotent on id, so re-ingesting
        a paper overwrites rather than duplicates — matching the idempotency we
        enforce in Postgres."""
        if not ids:
            return
        self._collection.upsert(
            ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
        )
        logger.info("vector_store: upserted %d vectors", len(ids))

    def query(
        self,
        embedding: list[float],
        top_k: int = 8,
        where: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        """Nearest-neighbor search. `where` filters by metadata (e.g. restrict
        to one user's uploaded documents). Cosine distance is mapped to a
        similarity score of 1 - distance so higher is better everywhere upstream."""
        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        hits: list[VectorHit] = []
        ids = result["ids"][0]
        docs = result["documents"][0]
        metas = result["metadatas"][0]
        dists = result["distances"][0]
        for cid, doc, meta, dist in zip(ids, docs, metas, dists, strict=True):
            hits.append(
                VectorHit(chroma_id=cid, text=doc, metadata=meta or {}, score=1.0 - dist)
            )
        return hits

    def delete(self, ids: list[str]) -> None:
        if ids:
            self._collection.delete(ids=ids)

    def count(self) -> int:
        return self._collection.count()
