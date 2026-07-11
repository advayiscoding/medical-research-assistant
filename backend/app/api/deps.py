"""FastAPI dependency providers — the composition root.

Everything injectable is wired here so routes declare *what* they need, not
*how* to build it. This is the seam that makes routes testable: a test overrides
`get_pubmed_client` with a fake, and the route never knows the difference.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User
from app.services.llm import ClaudeClient, get_claude_client
from app.services.pubmed import PubMedClient
from app.services.vector_store import VectorStore
from app.services.vector_store_provider import get_vector_store

# auto_error=False: we raise our own 401 with a WWW-Authenticate header rather
# than letting HTTPBearer raise a terse 403 on a missing header.
_bearer = HTTPBearer(auto_error=False)


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


def get_llm(
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> ClaudeClient:
    return get_claude_client(settings)


async def get_current_user(
    settings: Annotated[Settings, Depends(get_app_settings)],
    db: Annotated[AsyncSession, Depends(get_db)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """The guard for protected routes. Validates the Bearer token, loads the
    user, and returns it — or raises 401. Any route that declares CurrentUserDep
    is automatically protected; there is no way to forget the check because the
    user object is the thing the handler needs."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None:
        raise unauthorized
    user_id = decode_access_token(creds.credentials, settings)
    if user_id is None:
        raise unauthorized
    user = await db.get(User, user_id)
    if user is None:
        raise unauthorized  # token valid but user deleted
    return user


# Short aliases for readable route signatures.
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
PubMedDep = Annotated[PubMedClient, Depends(get_pubmed_client)]
VectorStoreDep = Annotated[VectorStore, Depends(get_store)]
LLMDep = Annotated[ClaudeClient, Depends(get_llm)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
