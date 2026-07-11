"""Embedding generation via SentenceTransformers.

An embedding is a fixed-length vector (384 numbers for MiniLM) positioning a
piece of text in "meaning space", where semantically similar texts land close
together. This is what powers semantic search: we embed the question and find
chunks whose vectors are nearest.

Design decisions
----------------
* Local model, not a hosted embedding API. For short chunks, MiniLM on CPU is
  fast (milliseconds) and free, with no per-call cost, no extra vendor key, and
  no outbound dependency on the search hot path. Hosted embeddings (OpenAI,
  Voyage) are marginally better on hard cases but add all of the above.
* Lazy singleton. Loading the model reads ~90 MB from disk and takes a second
  or two; we do it once per process, on first use, then reuse. Loading it per
  request would be catastrophic.
* Off the event loop. model.encode() is CPU-bound and would block FastAPI's
  async loop, stalling every concurrent request. We run it via asyncio.to_thread
  so the loop stays responsive.
* Normalized embeddings. We L2-normalize so that cosine similarity reduces to a
  dot product, and configure Chroma for cosine distance — the standard, scale-
  invariant choice for text embeddings.

The model name lives in config; swapping to a biomedical model
(pubmedbert-base-embeddings, 768-dim) changes one env var. Because different
models produce incompatible vector spaces, the Chroma collection name is
versioned by model (see vector_store.py) so vectors are never mixed.
"""

import asyncio
import logging
import threading
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_model_lock = threading.Lock()


def _dim(model: SentenceTransformer) -> int:
    # sentence-transformers renamed this method; support both across versions.
    if hasattr(model, "get_embedding_dimension"):
        return int(model.get_embedding_dimension())
    return int(model.get_sentence_embedding_dimension())


@lru_cache(maxsize=1)
def _load_model(model_name: str) -> SentenceTransformer:
    logger.info("Loading embedding model %s (first use)…", model_name)
    model = SentenceTransformer(model_name)
    logger.info("Embedding model ready: dim=%d", _dim(model))
    return model


def get_model() -> SentenceTransformer:
    # Double-checked locking: concurrent first-callers must not each load the
    # model. lru_cache is thread-safe for returning, but the initial heavy load
    # is guarded so it happens exactly once.
    settings = get_settings()
    with _model_lock:
        return _load_model(settings.embedding_model)


def embedding_dimension() -> int:
    return _dim(get_model())


def _encode_sync(texts: list[str]) -> list[list[float]]:
    model = get_model()
    vectors = model.encode(
        texts,
        normalize_embeddings=True,  # -> cosine similarity == dot product
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return vectors.tolist()


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Empty input returns []."""
    if not texts:
        return []
    return await asyncio.to_thread(_encode_sync, texts)


async def embed_query(text: str) -> list[float]:
    """Embed a single query string. Uses the same model/normalization as
    ingestion — query and documents MUST be embedded identically or distances
    are meaningless."""
    result = await embed_texts([text])
    return result[0]
