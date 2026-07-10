"""All models imported here so Base.metadata sees every table — Alembic
autogenerate diffs against this metadata, and a model it can't see is a table
it will try to drop."""

from app.models.chat import ChatMessage, ChatSession, Citation
from app.models.paper import Document, Paper, PaperChunk
from app.models.search import SearchHistory
from app.models.user import User

__all__ = [
    "ChatMessage",
    "ChatSession",
    "Citation",
    "Document",
    "Paper",
    "PaperChunk",
    "SearchHistory",
    "User",
]
