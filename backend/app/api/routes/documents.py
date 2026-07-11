"""PDF upload + document listing — Feature 9. All protected.

Upload flow (synchronous for portfolio scale; a queue would decouple it in
production):
    receive file -> size/type guard -> create Document(status=processing)
    -> extract text -> ingest (chunk/embed/store) -> status=ready
Any failure flips the row to status=failed with a message, so the UI can show
what went wrong instead of a dead spinner. The Document row is always created
first, so a failed upload is still visible and retryable rather than vanishing.
"""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep, SettingsDep, VectorStoreDep
from app.models import Document
from app.schemas.document import DocumentRead, DocumentUploadResponse
from app.services.ingestion import ingest_document
from app.services.pdf import PdfError, extract_text

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    user: CurrentUserDep,
    db: DbDep,
    store: VectorStoreDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
) -> DocumentUploadResponse:
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File exceeds {settings.max_upload_bytes // (1024 * 1024)} MB limit.",
        )
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file.")

    document = Document(
        user_id=user.id,
        filename=file.filename or "upload.pdf",
        title=(file.filename or "Untitled").rsplit(".", 1)[0],
        status="processing",
    )
    db.add(document)
    await db.flush()

    chunks_created = 0
    try:
        text = await extract_text(data)
        chunks_created = await ingest_document(db, document, text, store)
        document.status = "ready"
    except PdfError as exc:
        # Expected, user-facing failure (bad/scanned PDF). Persist the reason.
        document.status = "failed"
        document.error = str(exc)
        logger.info("document %s failed: %s", document.id, exc)
    except Exception as exc:  # unexpected — record and re-raise as 500
        document.status = "failed"
        document.error = "Internal error during processing."
        await db.commit()
        logger.exception("document %s crashed", document.id)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Processing failed") from exc

    await db.commit()
    return DocumentUploadResponse(
        document=DocumentRead.model_validate(document), chunks_created=chunks_created
    )


@router.get("", response_model=list[DocumentRead])
async def list_documents(user: CurrentUserDep, db: DbDep) -> list[DocumentRead]:
    result = await db.execute(
        select(Document).where(Document.user_id == user.id).order_by(Document.created_at.desc())
    )
    return [DocumentRead.model_validate(d) for d in result.scalars().all()]


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(document_id: uuid.UUID, user: CurrentUserDep, db: DbDep) -> DocumentRead:
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == user.id)
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return DocumentRead.model_validate(document)
