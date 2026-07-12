"""Chat persistence: sessions, messages, and running RAG inside a session.

This is where conversation history becomes durable and where the citation audit
trail is written to Postgres. Ownership is enforced on every access — a user can
only touch their own sessions — so authorization lives in the service, not just
the route.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import ChatMessage, ChatSession, Citation, PaperChunk, User
from app.services.library import fetch_store_ingest
from app.services.llm import LLMClient
from app.services.rag import answer_question
from app.services.retrieval import retrieve
from app.services.sources.base import SourceProvider
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)

# How many prior turns to feed the model as context. Bounded so a long session
# doesn't blow the context window or cost; recent turns carry the most signal.
HISTORY_TURNS = 6

# If the best locally-indexed chunk scores below this, the corpus doesn't really
# cover the question — so we fetch fresh papers from all sources before answering.
# Tuned above the retrieval floor (0.25): an off-topic-but-medical chunk can
# clear the floor yet still be irrelevant (a diabetes question matching a
# schizophrenia chunk at ~0.3), which is exactly the case this guards against.
CORPUS_COVERAGE_THRESHOLD = 0.45
AUTO_FETCH_PAPERS = 5


class SessionNotFound(Exception):
    """Session doesn't exist or isn't owned by this user (same error for both,
    so we never reveal that someone else's session id exists)."""


async def create_session(db: AsyncSession, user: User) -> ChatSession:
    session = ChatSession(user_id=user.id)
    db.add(session)
    await db.flush()
    return session


async def list_sessions(db: AsyncSession, user: User) -> list[ChatSession]:
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_session(db: AsyncSession, user: User, session_id: uuid.UUID) -> ChatSession:
    # Eager-load the full citation chain (message -> citation -> chunk -> paper)
    # so serialization needs no extra queries and never triggers lazy-load on a
    # closed async session (a classic async-ORM footgun).
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.id == session_id, ChatSession.user_id == user.id)
        .options(
            selectinload(ChatSession.messages)
            .selectinload(ChatMessage.citations)
            .selectinload(Citation.message)  # keep identity map warm
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise SessionNotFound(str(session_id))
    return session


async def load_message_citations(
    db: AsyncSession, message: ChatMessage
) -> list[tuple[int, PaperChunk, object]]:
    """Resolve a message's stored citations to (marker, chunk, paper) tuples for
    serialization. Separate query keeps get_session's load graph shallow."""
    result = await db.execute(
        select(Citation, PaperChunk)
        .join(PaperChunk, Citation.chunk_id == PaperChunk.id)
        .where(Citation.message_id == message.id)
        .order_by(Citation.marker)
        .options(selectinload(PaperChunk.paper))
    )
    out = []
    for citation, chunk in result.all():
        out.append((citation.marker, chunk, chunk.paper))
    return out


async def post_message(
    db: AsyncSession,
    user: User,
    session_id: uuid.UUID,
    question: str,
    store: VectorStore,
    llm: LLMClient,
    top_k: int = 5,
    providers: list[SourceProvider] | None = None,
) -> tuple[ChatMessage, ChatMessage, bool]:
    """Persist the user's question, run grounded RAG with recent history, persist
    the assistant's answer and its citations. Returns (user_msg, assistant_msg,
    insufficient_evidence).

    If source providers are supplied and the local corpus doesn't cover the
    question, we fetch and index relevant papers from all sources first — so a
    user can ask about a topic they never explicitly searched and still get a
    grounded answer, instead of a confusing 'the sources are about something
    else' reply."""
    session = await get_session(db, user, session_id)

    history = _recent_history(session)

    user_msg = ChatMessage(session_id=session.id, role="user", content=question)
    db.add(user_msg)

    # First user turn names the session (trimmed) so the sidebar is scannable.
    if not session.messages:
        session.title = question[:80]

    if providers is not None:
        await _ensure_corpus_covers(db, question, store, providers)

    result = await answer_question(question, store, llm, top_k=top_k, history=history)

    assistant_msg = ChatMessage(
        session_id=session.id, role="assistant", content=result.answer
    )
    db.add(assistant_msg)
    await db.flush()  # need assistant_msg.id before adding citations

    await _persist_citations(db, assistant_msg, result.citations)
    logger.info("session %s: answered (%d citations)", session_id, len(result.citations))
    return user_msg, assistant_msg, result.insufficient_evidence


async def _ensure_corpus_covers(
    db: AsyncSession,
    question: str,
    store: VectorStore,
    providers: list[SourceProvider],
) -> None:
    """If the indexed corpus doesn't already cover the question, run a federated
    search across all sources and ingest the results so the subsequent RAG pass
    has real evidence.

    Cheap coverage probe: one local vector search. If the top hit is confidently
    relevant, we skip the network fan-out entirely — follow-ups about an
    already-indexed topic stay fast."""
    hits = await retrieve(question, store, top_k=1)
    if hits and hits[0].score >= CORPUS_COVERAGE_THRESHOLD:
        return  # already covered; no fetch needed

    logger.info("corpus thin for %r (best=%.3f); federating across sources",
                question, hits[0].score if hits else 0.0)
    await fetch_store_ingest(db, store, providers, question, final_limit=AUTO_FETCH_PAPERS)


def _recent_history(session: ChatSession) -> list[tuple[str, str]]:
    turns = [(m.role, m.content) for m in session.messages]
    return turns[-HISTORY_TURNS:]


async def _persist_citations(db: AsyncSession, message: ChatMessage, citations: list) -> None:
    """Write citation rows linking the assistant message to real paper_chunks.

    The RAG Citation carries a chroma_id; we resolve it to the Postgres
    paper_chunks row so the FK chain (citation -> chunk -> paper) is intact and
    the audit trail is queryable. A chunk we can't resolve is skipped rather than
    faked — integrity over completeness."""
    chroma_ids = [c.chunk.chroma_id for c in citations]
    if not chroma_ids:
        return
    rows = await db.execute(select(PaperChunk).where(PaperChunk.chroma_id.in_(chroma_ids)))
    by_chroma = {r.chroma_id: r for r in rows.scalars().all()}

    for c in citations:
        chunk = by_chroma.get(c.chunk.chroma_id)
        if chunk is None:
            logger.warning("citation chunk %s not in Postgres; skipping", c.chunk.chroma_id)
            continue
        db.add(Citation(message_id=message.id, chunk_id=chunk.id, marker=c.marker))
