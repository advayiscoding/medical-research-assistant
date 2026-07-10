"""Tests for the RAG pipeline and its hallucination controls.

Citation resolution is unit-tested directly (it's the highest-risk logic — a
wrong mapping presents a fabricated source as real). The end-to-end test uses
real embeddings + real ChromaDB but a FAKE LLM, so we assert the grounding
behavior (floor, prompt assembly, citation attribution) without spending tokens
or depending on model wording.
"""

import uuid

import pytest

from app.schemas.retrieval import RetrievedChunk
from app.services import prompts
from app.services.rag import _resolve_citations, answer_question
from app.services.vector_store import VectorStore

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _chunk(cid: str, text: str, pmid: str) -> RetrievedChunk:
    return RetrievedChunk(chunk_id=None, chroma_id=cid, text=text, score=0.9,
                          source_type="paper", pmid=pmid, title="T", journal="J", year=2023)


# --- citation resolution (pure) ---------------------------------------------

def test_resolves_valid_markers_in_order() -> None:
    chunks = [_chunk("a", "x", "1"), _chunk("b", "y", "2"), _chunk("c", "z", "3")]
    answer = "Claim one [2]. Claim two [1] and again [1]."
    cites = _resolve_citations(answer, chunks)
    # First-appearance order, deduped: [2] then [1].
    assert [c.marker for c in cites] == [2, 1]
    assert cites[0].chunk.pmid == "2"
    assert cites[1].chunk.pmid == "1"


def test_drops_dangling_citations() -> None:
    chunks = [_chunk("a", "x", "1")]
    answer = "Supported [1]. Fabricated reference [9]."
    cites = _resolve_citations(answer, chunks)
    assert [c.marker for c in cites] == [1]  # [9] dropped, only 1 source sent


def test_no_citations_returns_empty() -> None:
    assert _resolve_citations("No brackets here.", [_chunk("a", "x", "1")]) == []


# --- prompt assembly --------------------------------------------------------

def test_context_block_is_numbered_and_self_describing() -> None:
    block = prompts.build_context_block([_chunk("a", "Metformin lowers glucose.", "12345")])
    assert "[1]" in block
    assert "PMID 12345" in block
    assert "Metformin lowers glucose." in block


# --- end-to-end with fake LLM ----------------------------------------------

class FakeLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.last_system: str | None = None
        self.last_user: str | None = None

    async def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> str:
        self.last_system, self.last_user = system, user
        return self.reply


@pytest.fixture
def store(tmp_path) -> VectorStore:
    from app.core.config import Settings
    return VectorStore(Settings(chroma_persist_dir=str(tmp_path / "chroma")))


async def test_insufficient_evidence_skips_llm(store: VectorStore) -> None:
    # Empty store -> nothing retrieved -> must NOT call the LLM.
    llm = FakeLLM("this should never be returned")
    resp = await answer_question("anything about nothing", store, llm)
    assert resp.insufficient_evidence is True
    assert resp.citations == []
    assert llm.last_user is None  # LLM was never called


async def test_grounded_answer_attributes_citations(store: VectorStore) -> None:
    from app.services import embeddings

    # Seed one real vector so retrieval returns it.
    text = "Metformin reduces hepatic glucose production and is first-line for type 2 diabetes."
    vec = await embeddings.embed_texts([text])
    cid = f"paper:{uuid.uuid4()}:0"
    store.add([cid], vec, [text],
              [{"source_type": "paper", "pmid": "999", "title": "Metformin review",
                "journal": "Diabetes Care", "year": 2023, "chunk_index": 0}])

    llm = FakeLLM("Metformin lowers blood glucose [1].")
    resp = await answer_question("How does metformin work?", store, llm)

    assert resp.insufficient_evidence is False
    assert len(resp.citations) == 1
    assert resp.citations[0].chunk.pmid == "999"
    # The grounding contract was actually sent to the model.
    assert "ONLY" in llm.last_system
    assert "Metformin reduces hepatic glucose" in llm.last_user
