"""Tests for the LangGraph research workflow.

Two levels:
  1. The routing functions (pure) — the loop-back and short-circuit logic is the
     highest-risk part, so it's asserted directly and deterministically.
  2. The whole compiled graph, driven with fakes: a scripted LLM that FAILS
     fact-check once then PASSES, proving the reflection cycle actually loops
     back to the summarizer and still terminates.
"""

import uuid

import pytest

from app.agents.graph import _route_after_factcheck, _route_after_retrieval, build_graph
from app.agents.nodes import ResearchAgents
from app.schemas.retrieval import RetrievedChunk
from app.services.vector_store import VectorStore

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# --- routing (pure) ---------------------------------------------------------

def _chunk() -> RetrievedChunk:
    return RetrievedChunk(chunk_id=None, chroma_id="c", text="t", score=0.9,
                          source_type="paper", pmid="1", title="T", journal="J", year=2023)


def test_route_retrieval_short_circuits_when_empty() -> None:
    assert _route_after_retrieval({"retrieved": []}) == "insufficient"
    assert _route_after_retrieval({"retrieved": [_chunk()]}) == "summarize"


def test_route_factcheck_loops_on_fail_then_stops_at_max() -> None:
    # fail with attempts remaining -> loop back to summarize
    assert _route_after_factcheck({"verdict": "fail", "attempts": 1, "max_factcheck_loops": 2}) == "summarize"
    # pass -> report
    assert _route_after_factcheck({"verdict": "pass", "attempts": 1, "max_factcheck_loops": 2}) == "report"
    # fail but exhausted -> report anyway (bounded loop, no infinite spin)
    assert _route_after_factcheck({"verdict": "fail", "attempts": 2, "max_factcheck_loops": 2}) == "report"


# --- whole-graph integration with fakes ------------------------------------

class FakePubMed:
    # Returns no papers → search ingests nothing; the corpus is pre-seeded below.
    async def search_and_fetch(self, query: str, max_results: int = 5):
        return []


class ScriptedLLM:
    """Routes replies by system-prompt identity and fails fact-check exactly once."""

    def __init__(self) -> None:
        self.summarize_calls = 0
        self.factcheck_calls = 0

    async def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> str:
        if "medical librarian" in system:
            return "alzheimer treatment"
        if "research analyst" in system:  # summarize
            self.summarize_calls += 1
            return "Lecanemab slows decline [1]."
        if "fact-checker" in system:
            self.factcheck_calls += 1
            # Fail the first draft, pass the corrected one → exercises the loop.
            return "VERDICT: FAIL\n- claim [1] overstates the effect size" \
                if self.factcheck_calls == 1 else "VERDICT: PASS"
        if "final answer" in system:  # report
            return "Lecanemab modestly slows cognitive decline in early AD [1]."
        return "VERDICT: PASS"


@pytest.fixture
def session_factory():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.core.config import get_settings
    engine = create_async_engine(get_settings().database_url)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def seeded_store(tmp_path) -> VectorStore:
    from app.core.config import Settings
    return VectorStore(Settings(chroma_persist_dir=str(tmp_path / "chroma")))


async def test_full_graph_loops_back_then_reports(seeded_store, session_factory) -> None:
    from app.services import embeddings

    # Pre-seed one real vector so retrieval returns a chunk.
    text = "Lecanemab reduced amyloid burden and slowed CDR-SB decline in early Alzheimer disease."
    vec = await embeddings.embed_texts([text])
    seeded_store.add([f"paper:{uuid.uuid4()}:0"], vec, [text],
                     [{"source_type": "paper", "pmid": "36449413", "title": "Lecanemab trial",
                       "journal": "NEJM", "year": 2023, "chunk_index": 0}])

    llm = ScriptedLLM()
    agents = ResearchAgents(FakePubMed(), seeded_store, llm, session_factory)
    graph = build_graph(agents)

    final = await graph.ainvoke({
        "question": "How effective is lecanemab for Alzheimer's?",
        "max_papers": 3, "top_k": 5, "max_factcheck_loops": 2, "attempts": 0,
    })

    # The fact-check loop fired: summarizer ran twice (initial + one correction).
    assert llm.summarize_calls == 2
    assert llm.factcheck_calls == 2
    assert final["verdict"] == "pass"
    assert final["insufficient_evidence"] is False
    assert "Lecanemab" in final["final_report"]
    assert len(final["citations"]) == 1
    assert final["citations"][0].chunk.pmid == "36449413"


async def test_full_graph_insufficient_evidence(seeded_store, session_factory) -> None:
    # Empty store → retrieval returns nothing → short-circuit, LLM never drafts.
    llm = ScriptedLLM()
    agents = ResearchAgents(FakePubMed(), seeded_store, llm, session_factory)
    graph = build_graph(agents)

    final = await graph.ainvoke({
        "question": "an obscure topic with no indexed evidence",
        "max_papers": 3, "top_k": 5, "max_factcheck_loops": 2, "attempts": 0,
    })

    assert final["insufficient_evidence"] is True
    assert final["citations"] == []
    assert llm.summarize_calls == 0  # never drafted
