"""Async engine and session management.

One engine per process (it owns the connection pool); one session per request.
The get_db dependency yields a session and guarantees it is closed, so a
request can never leak a connection. Commit is explicit in services —
autocommit hides transaction boundaries and makes multi-write consistency
accidental rather than designed.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        # In tests the app runs under the sync TestClient, which drives each
        # request on a short-lived event loop; pooled asyncpg connections would
        # outlive their loop and blow up. NullPool opens a fresh connection per
        # use, sidestepping that entirely. Production keeps a real pool.
        if settings.environment == "test":
            _engine = create_async_engine(settings.database_url, echo=False, poolclass=NullPool)
        else:
            _engine = create_async_engine(
                settings.database_url,
                echo=False,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,  # detect dropped connections before use
            )
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request."""
    async with get_session_factory()() as session:
        yield session


async def dispose_engine() -> None:
    """Called on app shutdown to close the pool cleanly."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
