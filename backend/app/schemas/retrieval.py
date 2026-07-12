"""Schemas for retrieval results.

A RetrievedChunk is the currency passed from the vector layer up into RAG and
the agents. It carries everything needed to (a) build LLM context and (b) form
a citation, without any further DB lookups: the chunk text, its similarity
score, and its source identity (PMID/title/journal).
"""

from pydantic import BaseModel


class RetrievedChunk(BaseModel):
    chunk_id: str | None  # Postgres paper_chunks.id (None if not yet linked)
    chroma_id: str
    text: str
    score: float
    source_type: str  # "paper" | "document"
    pmid: str | None = None
    doi: str | None = None
    title: str = ""
    journal: str = ""
    year: int | None = None
    # Federated-source provenance: which API(s) this paper came from, its
    # canonical URL, and its citation count — so every cited document names its
    # source, per the requirement.
    source: str = ""  # primary source: "pubmed", "openalex", …
    sources: list[str] = []  # every source that returned it
    url: str | None = None
    citation_count: int = 0


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = 5


class RetrieveResponse(BaseModel):
    query: str
    chunks: list[RetrievedChunk]
