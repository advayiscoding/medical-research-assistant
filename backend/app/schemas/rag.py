"""API schemas for the RAG question-answering endpoint."""

from pydantic import BaseModel, Field

from app.schemas.retrieval import RetrievedChunk


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=12)


class Citation(BaseModel):
    """One resolved [n] marker: which number, and the source it points to."""

    marker: int
    chunk: RetrievedChunk


class AskResponse(BaseModel):
    question: str
    answer: str
    citations: list[Citation]
    # True when retrieval found nothing above the relevance floor, so we
    # declined to call the LLM at all. The frontend can render this distinctly.
    insufficient_evidence: bool
