"""PDF extraction tests using real generated PDFs (reportlab) — no mocks.

Covers the happy path plus the three failure modes the service guards against:
non-PDF bytes, and text-less (scanned-like) PDFs. Encryption is exercised
indirectly via the is_encrypted branch in code review; generating an encrypted
PDF is left out to keep the fixture simple.
"""

import io

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.services.pdf import PdfError, extract_text

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _make_pdf(text: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    y = 750
    for line in text.split("\n"):
        c.drawString(72, y, line)
        y -= 18
    c.save()
    return buf.getvalue()


def _make_empty_pdf() -> bytes:
    buf = io.BytesIO()
    canvas.Canvas(buf, pagesize=letter).save()  # a page with no text
    return buf.getvalue()


async def test_extracts_text_from_valid_pdf() -> None:
    body = "Metformin reduces hepatic gluconeogenesis.\n" * 5
    text = await extract_text(_make_pdf(body))
    assert "Metformin" in text
    assert "gluconeogenesis" in text


async def test_rejects_non_pdf() -> None:
    with pytest.raises(PdfError, match="not a valid PDF"):
        await extract_text(b"this is plainly not a pdf file at all")


async def test_rejects_textless_pdf() -> None:
    with pytest.raises(PdfError, match="No extractable text"):
        await extract_text(_make_empty_pdf())
