"""Document (uploaded PDF) API schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    # UUID so model_validate() maps straight from the ORM row (see chat schema).
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    title: str | None
    status: str  # pending | processing | ready | failed
    error: str | None
    created_at: datetime


class DocumentUploadResponse(BaseModel):
    document: DocumentRead
    chunks_created: int
