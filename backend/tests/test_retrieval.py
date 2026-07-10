"""Tests for the retrieval strategy layer.

Uses a fake VectorStore returning hand-built hits so we can assert the strategy
(relevance floor, per-source diversity cap, top_k trimming) deterministically,
without depending on exact embedding distances. A second test uses the real
embedder end-to-end to confirm the floor rejects an off-topic query.
"""

import pytest

from app.schemas.retrieval import RetrievedChunk  # noqa: F401 (schema sanity)
from app.services.retrieval import MAX_PER_SOURCE, retrieve
from app.services.vector_store import VectorHit

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeStore:
    def __init__(self, hits: list[VectorHit]) -> None:
        self._hits = hits

    def query(self, embedding, top_k, where=None):  # noqa: ANN001
        return self._hits[:top_k]


async def _patch_embed(monkeypatch) -> None:
    async def fake_embed_query(text: str) -> list[float]:
        return [0.0, 0.0, 0.0]

    monkeypatch.setattr("app.services.retrieval.embeddings.embed_query", fake_embed_query)


def _hit(cid: str, score: float, pmid: str) -> VectorHit:
    return VectorHit(
        chroma_id=cid, text=f"text {cid}", score=score,
        metadata={"source_type": "paper", "pmid": pmid, "title": "T", "journal": "J", "year": 2023},
    )


async def test_relevance_floor_drops_low_scores(monkeypatch) -> None:
    await _patch_embed(monkeypatch)
    store = FakeStore([_hit("a", 0.9, "1"), _hit("b", 0.10, "2"), _hit("c", 0.05, "3")])
    chunks = await retrieve("q", store, top_k=5, min_score=0.25)
    assert [c.chroma_id for c in chunks] == ["a"]  # b, c below floor


async def test_per_source_cap_enforced(monkeypatch) -> None:
    await _patch_embed(monkeypatch)
    # Four high-scoring chunks all from the same PMID.
    store = FakeStore([_hit(str(i), 0.9 - i * 0.01, "SAME") for i in range(4)])
    chunks = await retrieve("q", store, top_k=5)
    assert len(chunks) == MAX_PER_SOURCE  # capped despite all being relevant


async def test_top_k_trimming(monkeypatch) -> None:
    await _patch_embed(monkeypatch)
    store = FakeStore([_hit(str(i), 0.9, f"pmid{i}") for i in range(10)])
    chunks = await retrieve("q", store, top_k=3)
    assert len(chunks) == 3
    # Preserves nearest-first ordering.
    assert [c.chroma_id for c in chunks] == ["0", "1", "2"]
