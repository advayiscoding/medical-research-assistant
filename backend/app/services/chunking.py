"""Text cleaning and chunking.

Why chunk at all? Two hard constraints:

1. Embedding models have a token limit (~256-512 tokens for MiniLM). Feeding a
   whole paper produces a truncated, mushy vector that represents nothing well.
2. Retrieval precision. If we embed a whole 4,000-word paper as one vector, a
   query about one narrow finding matches the *average* of the paper, burying
   the relevant paragraph. Small chunks let us retrieve exactly the passage
   that answers the question — which is also what makes citations precise.

Strategy: recursive character splitting with overlap.
  - Target ~1,200 chars (~250-300 tokens) — comfortably under the model limit
    while keeping enough context for a coherent passage.
  - 200-char overlap so a sentence straddling a boundary survives whole in at
    least one chunk (otherwise a fact split across the seam is retrievable by
    neither chunk).
  - Split on the *largest* natural boundary that keeps chunks under target:
    paragraphs first, then sentences, then words. We never split mid-word.

Why hand-rolled instead of LangChain's splitter: it's ~40 lines, has no hidden
behavior, and teaches the actual algorithm. The interface (clean + chunk) is
identical, so swapping in a library splitter later is trivial.
"""

import re

DEFAULT_CHUNK_SIZE = 1200
DEFAULT_OVERLAP = 200

# Separators tried in order, largest semantic unit first.
_SEPARATORS = ["\n\n", "\n", ". ", " "]

_WHITESPACE_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """Normalize whitespace without destroying paragraph structure.

    PubMed abstracts and PDF extractions arrive with ragged spacing, hyphenated
    line breaks, and stray control characters. We collapse runs of spaces/tabs,
    cap consecutive newlines at two (paragraph boundary), strip control chars,
    and repair words hyphenated across line breaks ("inflamma-\ntion" ->
    "inflammation"), which are common in PDF text and otherwise corrupt tokens.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # de-hyphenate across line breaks
    # Drop control chars but keep newlines and tabs — tabs are whitespace and
    # get normalized to spaces below; stripping them here would fuse words.
    text = "".join(ch for ch in text if ch in "\n\t" or ch >= " ")
    text = _WHITESPACE_RE.sub(" ", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """Split cleaned text into overlapping chunks on natural boundaries.

    Returns [] for empty input and [text] for text already under chunk_size —
    short abstracts stay whole, which is what we want (a 200-word abstract is
    one coherent unit).
    """
    text = clean_text(text)
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    # Build atomic segments by splitting on the finest separator that yields
    # pieces under chunk_size, so we never have to hard-cut mid-word.
    segments = _split_recursive(text, chunk_size)

    chunks: list[str] = []
    current = ""
    for seg in segments:
        if not current:
            current = seg
        elif len(current) + len(seg) + 1 <= chunk_size:
            current = f"{current} {seg}".strip()
        else:
            chunks.append(current)
            # Start next chunk with a tail of the previous one for overlap.
            tail = current[-overlap:] if overlap else ""
            current = f"{tail} {seg}".strip() if tail else seg
    if current:
        chunks.append(current)
    return chunks


def _split_recursive(text: str, chunk_size: int, sep_index: int = 0) -> list[str]:
    """Break text into segments each <= chunk_size, descending through
    separators. A segment still too large at the finest separator is hard-split
    as a last resort (pathological input with no spaces)."""
    if len(text) <= chunk_size:
        return [text]
    if sep_index >= len(_SEPARATORS):
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

    sep = _SEPARATORS[sep_index]
    parts = text.split(sep)
    segments: list[str] = []
    for part in parts:
        if len(part) <= chunk_size:
            if part.strip():
                segments.append(part.strip())
        else:
            segments.extend(_split_recursive(part, chunk_size, sep_index + 1))
    return segments
