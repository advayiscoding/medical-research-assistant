"""Prompt construction for grounded RAG.

Everything about *how we ask Claude to stay grounded* lives here, isolated from
the orchestration in rag.py. Keeping the prompt as data (not f-strings sprinkled
through logic) makes it reviewable and testable, and means prompt-tuning never
risks touching control flow.

The grounding contract is enforced in three places (defense in depth — see
ARCHITECTURE.md §4):
  1. This system prompt forbids uncited claims.
  2. Context blocks are numbered so the model has concrete [n] handles.
  3. rag.py validates every [n] the model emits against the blocks we actually
     sent, stripping any that dangle.
"""

from app.schemas.retrieval import RetrievedChunk

SYSTEM_PROMPT = """\
You are a medical research assistant. You answer questions ONLY using the \
numbered source excerpts provided in the user's message. These excerpts come \
from peer-reviewed medical literature.

Rules — follow all of them:
1. Ground every factual claim in the sources. After each claim, cite the \
source(s) that support it with bracketed numbers, e.g. "Lecanemab reduced \
amyloid markers [1][3]."
2. Use ONLY the provided excerpts. Do not add facts from your own training \
data, even if you believe them correct. This system exists to prevent \
hallucination.
3. If the excerpts do not contain enough information to answer, say so plainly: \
"The retrieved sources do not contain enough evidence to answer this." Do not \
guess or pad.
4. Do not cite a source for a claim it does not actually support.
5. Be concise and clinical. Lead with the answer, then the supporting detail. \
Do not give medical advice or diagnoses — you summarize research, you do not \
practice medicine.
6. When sources disagree, say so and cite both sides."""


def build_context_block(chunks: list[RetrievedChunk]) -> str:
    """Render retrieved chunks as a numbered, self-describing source list.

    Each block leads with its citation number and provenance (PMID/journal/year)
    so the model can both cite it precisely and mention the source in prose.
    Numbering is 1-based to match how humans read citations."""
    if not chunks:
        return "(no sources retrieved)"
    parts: list[str] = []
    for i, c in enumerate(chunks, start=1):
        provenance = c.title or "Untitled"
        if c.pmid:
            provenance += f" — PMID {c.pmid}"
        if c.journal:
            provenance += f", {c.journal}"
        if c.year:
            provenance += f" ({c.year})"
        parts.append(f"[{i}] {provenance}\n{c.text}")
    return "\n\n".join(parts)


def build_history_block(history: list[tuple[str, str]]) -> str:
    """Render prior turns as compact conversation context so follow-up questions
    ("what about its side effects?") are interpretable. We cap length upstream;
    here we just format role-tagged lines."""
    lines = [f"{'User' if role == 'user' else 'Assistant'}: {content}" for role, content in history]
    return "\n".join(lines)


def build_user_message(
    question: str,
    chunks: list[RetrievedChunk],
    history: list[tuple[str, str]] | None = None,
) -> str:
    context = build_context_block(chunks)
    parts = [f"Sources:\n\n{context}\n\n---\n\n"]
    if history:
        # History is context for interpreting the question, NOT a source of
        # facts — the sources above remain the only citable evidence.
        parts.append(
            "Conversation so far (for context only — do not cite it):\n"
            f"{build_history_block(history)}\n\n---\n\n"
        )
    parts.append(
        f"Question: {question}\n\nAnswer using only the sources above, citing with [n]."
    )
    return "".join(parts)
