"""PDF text extraction — Feature 9's ingestion front-end.

Isolated like every external-format concern: pypdf appears only here. Extraction
is CPU-bound and can be slow on large files, so it runs off the event loop.

Validation is defense against three failure modes:
  1. Not a PDF (wrong magic bytes) — reject before pypdf chokes.
  2. Encrypted/corrupt PDF — surfaced as a clean error, not a 500.
  3. Image-only (scanned) PDF — extracts to near-empty text; we detect and
     report it rather than silently ingesting nothing. (OCR is future work.)
"""

import asyncio
import io
import logging

from pypdf import PdfReader

logger = logging.getLogger(__name__)

_PDF_MAGIC = b"%PDF-"
# Below this many characters we treat extraction as failed (likely scanned/image
# PDF with no text layer). A real abstract has hundreds of chars.
_MIN_USABLE_CHARS = 50


class PdfError(Exception):
    """Extraction failed for a reason worth showing the user."""


def _extract_sync(data: bytes) -> str:
    if not data.startswith(_PDF_MAGIC):
        raise PdfError("File is not a valid PDF.")
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # pypdf raises a variety of types on bad input
        raise PdfError(f"Could not read PDF: {exc}") from exc
    if reader.is_encrypted:
        # Try empty-password decrypt (common for "protected but not really" PDFs).
        try:
            reader.decrypt("")
        except Exception as exc:
            raise PdfError("PDF is encrypted and cannot be read.") from exc

    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # one bad page shouldn't kill the whole document
            continue
    text = "\n\n".join(pages).strip()

    if len(text) < _MIN_USABLE_CHARS:
        raise PdfError(
            "No extractable text found — the PDF may be scanned images (OCR not supported)."
        )
    return text


async def extract_text(data: bytes) -> str:
    """Extract text from PDF bytes. Raises PdfError with a user-facing message on
    any validation or extraction failure."""
    return await asyncio.to_thread(_extract_sync, data)
