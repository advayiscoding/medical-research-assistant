"""Integration tests for the schema's integrity rules.

These run against the real Postgres from docker-compose (constraints like
CHECK and JSONB are Postgres features — testing them on SQLite would test
nothing). Each test runs in a transaction that is rolled back, so the
database is left exactly as found.
"""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.models import Paper, PaperChunk, User

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def db():
    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()
    await engine.dispose()


async def test_paper_chunk_round_trip(db: AsyncSession) -> None:
    paper = Paper(
        pmid="12345678",
        title="A study of things",
        authors=["Smith J", "Doe A"],
        abstract="Background: things. Results: stuff.",
        journal="Nature Medicine",
    )
    db.add(paper)
    await db.flush()

    chunk = PaperChunk(paper_id=paper.id, chunk_index=0, text="Background: things.",
                       chroma_id=f"test-{uuid.uuid4()}")
    db.add(chunk)
    await db.flush()

    assert chunk.id is not None
    assert chunk.created_at is not None  # server_default fired


async def test_chunk_requires_exactly_one_source(db: AsyncSession) -> None:
    # No parent at all → CHECK constraint must reject
    db.add(PaperChunk(chunk_index=0, text="orphan", chroma_id=f"test-{uuid.uuid4()}"))
    with pytest.raises(IntegrityError):
        await db.flush()


async def test_duplicate_pmid_rejected(db: AsyncSession) -> None:
    db.add(Paper(pmid="99999999", title="one", authors=[]))
    await db.flush()
    db.add(Paper(pmid="99999999", title="two", authors=[]))
    with pytest.raises(IntegrityError):
        await db.flush()


async def test_duplicate_email_rejected(db: AsyncSession) -> None:
    db.add(User(email="dup@example.com", hashed_password="x"))
    await db.flush()
    db.add(User(email="dup@example.com", hashed_password="y"))
    with pytest.raises(IntegrityError):
        await db.flush()
