"""Typed state for the research agent graph.

A single object flows through every node; each node reads what it needs and
returns a partial dict that LangGraph merges into the state. Using a TypedDict
(rather than passing loose args between agents) is what makes the graph
inspectable and each node independently testable — you can hand any node a
hand-built state and assert on what it returns.

Channel semantics: our graph is sequential (no two nodes write the same key
concurrently), so the default last-write-wins overwrite is exactly right — no
custom reducers needed. If we later fan out retrieval across queries in
parallel, the chunk list would need an additive reducer; called out here so the
next engineer knows where that seam is.
"""

from typing import TypedDict

from app.schemas.rag import Citation
from app.schemas.retrieval import RetrievedChunk


class ResearchState(TypedDict, total=False):
    # --- inputs (set at invocation) ---
    question: str
    top_k: int
    max_papers: int
    max_factcheck_loops: int

    # --- Search agent output ---
    search_queries: list[str]
    papers_ingested: int

    # --- Retrieval agent output ---
    retrieved: list[RetrievedChunk]

    # --- Summarization agent output (rewritten each loop) ---
    draft_summary: str

    # --- Fact-check agent output ---
    verdict: str          # "pass" | "fail"
    corrections: str      # feedback fed back into summarization on a fail
    attempts: int         # fact-check iterations, bounds the loop

    # --- Report agent output (terminal) ---
    final_report: str
    citations: list[Citation]
    insufficient_evidence: bool
