"""FastAPI dependency providers — the composition root.

Everything injectable is wired here so routes declare *what* they need, not
*how* to build it. This is the seam that makes routes testable: a test overrides
`get_pubmed_client` with a fake, and the route never knows the difference.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.services.pubmed import PubMedClient
from app.services.vector_store import VectorStore
from app.services.vector_store_provider import get_vector_store


def get_app_settings(request: Request) -> Settings:
    # Prefer settings attached to the app (lets tests inject overrides);
    # fall back to the process-wide cached settings.
    return getattr(request.app.state, "settings", None) or get_settings()


async def get_pubmed_client(
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AsyncIterator[PubMedClient]:
    async with PubMedClient(settings) as client:
        yield client


def get_store() -> VectorStore:
    return get_vector_store()


# Short aliases for readable route signatures.
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
PubMedDep = Annotated[PubMedClient, Depends(get_pubmed_client)]
VectorStoreDep = Annotated[VectorStore, Depends(get_store)]
