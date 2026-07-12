"""Multi-agent research endpoint.

Runs the full LangGraph workflow: Search -> Retrieval -> Summarize ->
Fact-Check (with loop-back) -> Report. This is the heavyweight path for
"research this topic" questions; simple follow-ups should use /api/ask, which is
a single cheaper RAG pass (ARCHITECTURE.md §5).
"""

from fastapi import APIRouter

from app.agents.graph import build_graph
from app.agents.nodes import ResearchAgents
from app.api.deps import CurrentUserDep, LLMDep, SourceProvidersDep, VectorStoreDep
from app.db.session import get_session_factory
from app.schemas.research import ResearchRequest, ResearchResponse

router = APIRouter(prefix="/research", tags=["research"])


@router.post("", response_model=ResearchResponse)
async def research(
    payload: ResearchRequest,
    user: CurrentUserDep,
    providers: SourceProvidersDep,
    store: VectorStoreDep,
    llm: LLMDep,
) -> ResearchResponse:
    agents = ResearchAgents(providers, store, llm, get_session_factory())
    graph = build_graph(agents)

    final = await graph.ainvoke(
        {
            "question": payload.question,
            "max_papers": payload.max_papers,
            "top_k": payload.top_k,
            "max_factcheck_loops": payload.max_factcheck_loops,
            "attempts": 0,
        }
    )

    return ResearchResponse(
        question=payload.question,
        report=final.get("final_report", ""),
        citations=final.get("citations", []),
        insufficient_evidence=final.get("insufficient_evidence", False),
        search_queries=final.get("search_queries", []),
        papers_ingested=final.get("papers_ingested", 0),
        factcheck_attempts=final.get("attempts", 0),
        factcheck_verdict=final.get("verdict", ""),
    )
