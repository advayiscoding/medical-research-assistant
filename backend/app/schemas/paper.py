"""API-boundary schemas for papers and search.

Separate from ORM models on purpose (see ARCHITECTURE.md §2): these define the
JSON contract the frontend depends on. A DB column rename must not silently
change the API — if it should, that's a deliberate schema edit here.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydField


class PubMedPaper(BaseModel):
    """A paper as parsed from PubMed, before persistence."""

    pmid: str
    title: str
    authors: list[str] = PydField(default_factory=list)
    abstract: str | None = None
    journal: str | None = None
    publication_date: date | None = None


class PaperRead(BaseModel):
    """A persisted paper as returned to the client, including which federated
    source(s) it came from and its citation count."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    pmid: str | None
    doi: str | None = None
    title: str
    authors: list[str]
    abstract: str | None
    journal: str | None
    publication_date: date | None
    source: str = ""
    sources: list[str] = []
    citation_count: int = 0
    url: str | None = None
    is_preprint: bool = False


class SearchRequest(BaseModel):
    query: str = PydField(min_length=2, max_length=1000)
    max_results: int = PydField(default=10, ge=1, le=50)


class SearchResponse(BaseModel):
    query: str
    count: int
    papers: list[PaperRead]
