"""Chat endpoints — all protected. This is Feature 4 (chat) + Feature 8
(history) + the persisted half of Feature 5 (citations).

Every route declares CurrentUserDep, so the user is authenticated and the chat
service scopes all access to that user's own sessions.
"""

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUserDep, DbDep, LLMDep, PubMedDep, VectorStoreDep
from app.models import ChatMessage, Paper, PaperChunk
from app.schemas.chat import (
    MessageRead,
    PostMessageRequest,
    PostMessageResponse,
    SessionDetail,
    SessionRead,
)
from app.schemas.rag import Citation as CitationSchema
from app.schemas.retrieval import RetrievedChunk
from app.services import chat as chat_service
from app.services.chat import SessionNotFound

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/sessions", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(user: CurrentUserDep, db: DbDep) -> SessionRead:
    session = await chat_service.create_session(db, user)
    await db.commit()
    return SessionRead.model_validate(session)


@router.get("/sessions", response_model=list[SessionRead])
async def list_sessions(user: CurrentUserDep, db: DbDep) -> list[SessionRead]:
    sessions = await chat_service.list_sessions(db, user)
    return [SessionRead.model_validate(s) for s in sessions]


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(session_id: uuid.UUID, user: CurrentUserDep, db: DbDep) -> SessionDetail:
    try:
        session = await chat_service.get_session(db, user, session_id)
    except SessionNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found") from exc

    messages = [await _serialize_message(db, m) for m in session.messages]
    return SessionDetail(
        id=str(session.id),
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=messages,
    )


@router.post("/sessions/{session_id}/messages", response_model=PostMessageResponse)
async def post_message(
    session_id: uuid.UUID,
    payload: PostMessageRequest,
    user: CurrentUserDep,
    db: DbDep,
    store: VectorStoreDep,
    llm: LLMDep,
    pubmed: PubMedDep,
) -> PostMessageResponse:
    try:
        user_msg, assistant_msg, insufficient = await chat_service.post_message(
            db, user, session_id, payload.question, store, llm,
            top_k=payload.top_k, pubmed=pubmed,
        )
    except SessionNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found") from exc
    await db.commit()

    return PostMessageResponse(
        session_id=str(session_id),
        user_message=await _serialize_message(db, user_msg),
        assistant_message=await _serialize_message(db, assistant_msg),
        insufficient_evidence=insufficient,
    )


async def _serialize_message(db: DbDep, message: ChatMessage) -> MessageRead:
    """Turn a stored message + its citation rows into the API shape, rebuilding
    each citation's source metadata from the chunk/paper it references."""
    resolved = await chat_service.load_message_citations(db, message)
    citations: list[CitationSchema] = []
    for marker, chunk, paper in resolved:
        citations.append(
            CitationSchema(
                marker=marker,
                chunk=_chunk_to_schema(chunk, paper),
            )
        )
    return MessageRead(
        id=str(message.id),
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        citations=citations,
    )


def _chunk_to_schema(chunk: PaperChunk, paper: Paper | None) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=str(chunk.id),
        chroma_id=chunk.chroma_id,
        text=chunk.text,
        score=1.0,  # stored citation; original retrieval score not persisted
        source_type="paper" if paper else "document",
        pmid=paper.pmid if paper else None,
        title=paper.title if paper else "",
        journal=(paper.journal or "") if paper else "",
        year=(paper.publication_date.year if paper and paper.publication_date else None),
    )
