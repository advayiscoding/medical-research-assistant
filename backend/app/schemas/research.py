"""API schemas for the multi-agent research endpoint."""

from pydantic import BaseModel, Field

from app.schemas.rag import Citation


class ResearchRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    max_papers: int = Field(default=5, ge=1, le=15)
    top_k: int = Field(default=6, ge=1, le=12)
    max_factcheck_loops: int = Field(default=2, ge=0, le=4)


class ResearchResponse(BaseModel):
    question: str
    report: str
    citations: list[Citation]
    insufficient_evidence: bool
    # Observability into what the agents actually did — surfaced so the UI can
    # show the workflow, not just the final answer.
    search_queries: list[str]
    papers_ingested: int
    factcheck_attempts: int
    factcheck_verdict: str
