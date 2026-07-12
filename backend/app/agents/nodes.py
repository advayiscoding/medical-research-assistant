"""The five agent nodes.

Each node is an async method that reads the graph state and returns a partial
update. They are grouped in a class so the graph can inject the same
dependencies (PubMed, vector store, LLM, DB) into every node without globals —
which is also what makes them unit-testable with fakes.

The nodes deliberately reuse the Phase 3-6 services (pubmed, ingestion,
retrieval, prompts, citation resolution) rather than reimplementing them. An
agent workflow should orchestrate existing capabilities, not fork them.
"""

import logging
import re

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents import prompts
from app.agents.state import ResearchState
from app.services.library import fetch_store_ingest
from app.services.llm import LLMClient
from app.services.prompts import build_user_message
from app.services.rag import _resolve_citations
from app.services.retrieval import retrieve
from app.services.sources.base import SourceProvider
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)


class ResearchAgents:
    def __init__(
        self,
        providers: list[SourceProvider],
        store: VectorStore,
        llm: LLMClient,
        session_factory: async_sessionmaker,
    ) -> None:
        self._providers = providers
        self._store = store
        self._llm = llm
        self._session_factory = session_factory

    # --- 1. Search agent -------------------------------------------------
    async def search(self, state: ResearchState) -> ResearchState:
        """Decide what to search for, fetch it from all ten sources (deduped and
        ranked), and ingest it so it's retrievable. This is the agent's ability
        to *gather fresh evidence* rather than only reusing whatever happens to
        already be indexed."""
        queries = await self._plan_queries(state["question"])
        total = 0
        async with self._session_factory() as db:
            for q in queries:
                papers = await fetch_store_ingest(
                    db, self._store, self._providers, q,
                    final_limit=state.get("max_papers", 5),
                )
                total += len(papers)
            await db.commit()
        logger.info("search agent: %d queries, %d papers ingested", len(queries), total)
        return {"search_queries": queries, "papers_ingested": total}

    async def _plan_queries(self, question: str) -> list[str]:
        raw = await self._llm.complete(prompts.QUERY_PLANNER_SYSTEM, question, max_tokens=256)
        queries = [ln.strip(" -•\t") for ln in raw.splitlines() if ln.strip()]
        queries = [q for q in queries if len(q) > 3][:3]
        # Robustness: if the model returns nothing usable, fall back to the raw
        # question so the pipeline never stalls on an empty query set.
        return queries or [question]

    # --- 2. Retrieval agent ---------------------------------------------
    async def retrieval(self, state: ResearchState) -> ResearchState:
        chunks = await retrieve(state["question"], self._store, top_k=state.get("top_k", 6))
        return {"retrieved": chunks}

    # --- 3. Summarization agent -----------------------------------------
    async def summarize(self, state: ResearchState) -> ResearchState:
        """Draft a cited evidence summary. On a fact-check loop-back, the prior
        round's corrections are appended so the writer knows exactly what to
        fix — this is the 'reflection' the cycle exists for."""
        chunks = state["retrieved"]
        user = build_user_message(state["question"], chunks)
        corrections = state.get("corrections")
        if corrections:
            user += (
                "\n\n---\nA previous draft failed fact-checking for these reasons. "
                f"Fix them and cite carefully:\n{corrections}"
            )
        draft = await self._llm.complete(prompts.SUMMARIZE_SYSTEM, user)
        return {"draft_summary": draft}

    # --- 4. Fact-checking agent -----------------------------------------
    async def fact_check(self, state: ResearchState) -> ResearchState:
        """Re-read the draft against the sources and rule PASS/FAIL. This is a
        separate LLM call with a fresh, adversarial instruction — checking is a
        different task from writing, and separating them catches errors the
        writer is blind to."""
        chunks = state["retrieved"]
        sources = build_user_message("(verification)", chunks)
        prompt = (
            f"{sources}\n\n---\n\nDRAFT TO VERIFY:\n{state['draft_summary']}"
        )
        result = await self._llm.complete(prompts.FACT_CHECK_SYSTEM, prompt)
        verdict = "pass" if re.search(r"VERDICT:\s*PASS", result, re.IGNORECASE) else "fail"
        attempts = state.get("attempts", 0) + 1
        logger.info("fact-check agent: verdict=%s attempt=%d", verdict, attempts)
        return {"verdict": verdict, "corrections": result, "attempts": attempts}

    # --- 5. Report agent ------------------------------------------------
    async def report(self, state: ResearchState) -> ResearchState:
        """Produce the final, cited report from the verified summary and
        resolve its citations back to real sources."""
        chunks = state["retrieved"]
        user = (
            f"{build_user_message(state['question'], chunks)}\n\n---\n\n"
            f"Verified evidence summary:\n{state.get('draft_summary', '')}"
        )
        final = await self._llm.complete(prompts.REPORT_SYSTEM, user)
        citations = _resolve_citations(final, chunks)
        return {"final_report": final, "citations": citations, "insufficient_evidence": False}

    async def report_insufficient(self, state: ResearchState) -> ResearchState:
        """Terminal node when retrieval found nothing above the relevance floor —
        the agent equivalent of the RAG pipeline's hallucination control #1."""
        return {
            "final_report": "The retrieved sources do not contain enough evidence to "
            "answer this question. Try rephrasing or broadening the query.",
            "citations": [],
            "insufficient_evidence": True,
        }
