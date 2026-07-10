"""Unit tests for text cleaning and chunking — pure functions, no I/O."""

from app.services.chunking import chunk_text, clean_text


def test_clean_collapses_whitespace_keeps_paragraphs() -> None:
    raw = "Hello   world\t\ttab.\n\n\n\nNew  para."
    cleaned = clean_text(raw)
    assert cleaned == "Hello world tab.\n\nNew para."


def test_clean_dehyphenates_across_linebreaks() -> None:
    assert clean_text("inflamma-\ntion pathway") == "inflammation pathway"


def test_clean_strips_control_characters() -> None:
    assert "\x00" not in clean_text("bad\x00char")


def test_short_text_stays_whole() -> None:
    text = "A short abstract about a single finding."
    assert chunk_text(text) == [text]


def test_empty_text_yields_no_chunks() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_long_text_splits_with_overlap() -> None:
    # 30 sentences well over the default 1200-char target.
    text = " ".join(f"Sentence number {i} describes a distinct finding." for i in range(60))
    chunks = chunk_text(text, chunk_size=300, overlap=60)

    assert len(chunks) > 1
    assert all(len(c) <= 300 + 60 for c in chunks)  # size + overlap tail bound
    # Overlap: the tail of one chunk should appear at the head of the next.
    first_tail = chunks[0][-40:]
    assert any(word in chunks[1] for word in first_tail.split()[:3])


def test_no_word_is_split_midway() -> None:
    text = " ".join(["supercalifragilistic"] * 200)
    chunks = chunk_text(text, chunk_size=100, overlap=20)
    # Every chunk is whole words (no partial token at the edges).
    for c in chunks:
        for token in c.split():
            assert token == "supercalifragilistic"
