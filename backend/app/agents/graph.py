"""Graph wiring for the research workflow.

    START
      -> search           (plan queries, fetch + ingest fresh papers)
      -> retrieval        (vector search over the corpus)
      -> [has evidence?]  ── no ──> report_insufficient -> END
                          └─ yes ─> summarize
      -> summarize        (draft cited evidence summary)
      -> fact_check       (verify draft against sources)
      -> [pass or max?]   ── loop ──> summarize   (fix and retry)
                          └─ done ──> report -> END

Two conditional edges carry the design:
  * after retrieval — short-circuit to an honest "insufficient evidence" answer
    instead of asking downstream agents to summarize nothing (hallucination
    control, mirrored from the RAG pipeline).
  * after fact_check — the reflection cycle. A failed check loops back to the
    summarizer WITH the correction notes, bounded by max_factcheck_loops so a
    stubborn draft can't spin forever. This cycle is precisely why this is a
    LangGraph graph and not a linear function chain.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.nodes import ResearchAgents
from app.agents.state import ResearchState


def _route_after_retrieval(state: ResearchState) -> str:
    return "summarize" if state.get("retrieved") else "insufficient"


def _route_after_factcheck(state: ResearchState) -> str:
    passed = state.get("verdict") == "pass"
    exhausted = state.get("attempts", 0) >= state.get("max_factcheck_loops", 2)
    return "report" if (passed or exhausted) else "summarize"


def build_graph(agents: ResearchAgents) -> CompiledStateGraph:
    g: StateGraph = StateGraph(ResearchState)

    g.add_node("search", agents.search)
    g.add_node("retrieval", agents.retrieval)
    g.add_node("summarize", agents.summarize)
    g.add_node("fact_check", agents.fact_check)
    g.add_node("report", agents.report)
    g.add_node("insufficient", agents.report_insufficient)

    g.add_edge(START, "search")
    g.add_edge("search", "retrieval")
    g.add_conditional_edges(
        "retrieval",
        _route_after_retrieval,
        {"summarize": "summarize", "insufficient": "insufficient"},
    )
    g.add_edge("summarize", "fact_check")
    g.add_conditional_edges(
        "fact_check",
        _route_after_factcheck,
        {"summarize": "summarize", "report": "report"},
    )
    g.add_edge("report", END)
    g.add_edge("insufficient", END)

    return g.compile()
