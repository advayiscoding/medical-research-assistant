"""The RAG pipeline: retrieve -> ground -> generate -> attribute.

This ties Phases 5 and 6 together and is the function the chat endpoint and the
LangGraph report agent both call. It owns the hallucination controls end to end.

Flow (ARCHITECTURE.md §4):
    question
      -> retrieve() top-k relevant chunks
      -> if none clear the floor: return "insufficient evidence" (no LLM call)
      -> build grounded prompt, call Claude
      -> parse [n] markers, validate against the chunks we actually sent
      -> return answer + resolved citations
"""

import logging
import re

from app.schemas.rag import AskResponse, Citation
from app.services import prompts
from app.services.llm import LLMClient
from app.services.retrieval import retrieve
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)

# Matches [1], [12] etc. Bracketed integers are our citation contract with the
# model (the system prompt tells it to cite this way).
_CITATION_RE = re.compile(r"\[(\d+)\]")


async def answer_question(
    question: str,
    store: VectorStore,
    llm: LLMClient,
    top_k: int = 5,
    history: list[tuple[str, str]] | None = None,
) -> AskResponse:
    # Retrieval uses the raw question. For follow-ups this is a known limitation:
    # "what about its side effects?" retrieves poorly on its own. The clean fix
    # is a query-rewrite step (LLM condenses history+question into a standalone
    # query before retrieval); we pass history to the answer prompt for now and
    # note the rewrite as the next upgrade.
    chunks = await retrieve(question, store, top_k=top_k)

    # Hallucination control #1: the retrieval floor. If nothing relevant was
    # found, we do NOT ask the model — an ungrounded LLM would happily invent a
    # plausible-sounding medical answer. Refusing is the correct behavior.
    if not chunks:
        return AskResponse(
            question=question,
            answer="The retrieved sources do not contain enough evidence to answer this question.",
            citations=[],
            insufficient_evidence=True,
        )

    system = prompts.SYSTEM_PROMPT
    user = prompts.build_user_message(question, chunks, history=history)
    answer = await llm.complete(system, user)

    citations = _resolve_citations(answer, chunks)
    return AskResponse(
        question=question,
        answer=answer,
        citations=citations,
        insufficient_evidence=False,
    )


def _resolve_citations(answer: str, chunks: list) -> list[Citation]:
    """Map the [n] markers the model emitted back to the chunks we sent.

    Hallucination control #3 (post-hoc verification): we only trust markers that
    reference a source in range [1, len(chunks)]. A dangling [9] when we sent 5
    sources is dropped — the model referenced something it wasn't given, which
    we must not present as a real citation. Deduped and returned in first-appearance
    order so the citations panel reads naturally."""
    seen: set[int] = set()
    resolved: list[Citation] = []
    for match in _CITATION_RE.finditer(answer):
        marker = int(match.group(1))
        if marker in seen:
            continue
        if 1 <= marker <= len(chunks):
            seen.add(marker)
            resolved.append(Citation(marker=marker, chunk=chunks[marker - 1]))
        else:
            logger.warning("dropping dangling citation [%d] (only %d sources)", marker, len(chunks))
    return resolved
