"""RAG question-answering endpoint.

The user-facing surface of Phase 6. Thin as always: validate, call the RAG
service, return. Auth is layered on in Phase 7b; kept open now so the pipeline
is testable end to end first.
"""

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, LLMDep, VectorStoreDep
from app.schemas.rag import AskRequest, AskResponse
from app.services.rag import answer_question

router = APIRouter(prefix="/ask", tags=["ask"])


@router.post("", response_model=AskResponse)
async def ask(
    payload: AskRequest, user: CurrentUserDep, store: VectorStoreDep, llm: LLMDep
) -> AskResponse:
    return await answer_question(payload.question, store, llm, top_k=payload.top_k)
