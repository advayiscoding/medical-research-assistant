"""End-to-end ingestion test: paper -> chunks -> embeddings -> ChromaDB.

Exercises the real chunker, the real embedding model, and a real ChromaDB in a
temp directory — no mocks. Slower (loads the model once) but proves the whole
pipeline actually indexes and that ingestion is idempotent.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings, get_settings
from app.models import Paper, PaperChunk
from app.services.ingestion import ingest_paper
from app.services.vector_store import VectorStore

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


@pytest.fixture
def store(tmp_path) -> VectorStore:
    # Isolated Chroma per test run, thrown away with tmp_path.
    settings = Settings(chroma_persist_dir=str(tmp_path / "chroma"))
    return VectorStore(settings)


async def test_ingest_paper_creates_chunks_and_vectors(db: AsyncSession, store: VectorStore) -> None:
    abstract = " ".join(
        f"Finding {i}: the treatment reduced amyloid burden in cohort {i}." for i in range(40)
    )
    pmid = f"T{uuid.uuid4().int % 10_000_000}"
    paper = Paper(dedup_key=f"pmid:{pmid}", source="pubmed", sources=["pubmed"],
                  pmid=pmid, title="Amyloid study",
                  authors=["Doe A"], abstract=abstract, journal="Nature Medicine")
    db.add(paper)
    await db.flush()

    n = await ingest_paper(db, paper, store)
    assert n > 1  # long abstract splits into multiple chunks

    rows = (await db.execute(select(PaperChunk).where(PaperChunk.paper_id == paper.id))).scalars().all()
    assert len(rows) == n
    # Every Postgres chunk links to a Chroma vector by deterministic id.
    assert all(r.chroma_id == f"paper:{paper.id}:{r.chunk_index}" for r in rows)
    assert store.count() == n


async def test_ingest_is_idempotent(db: AsyncSession, store: VectorStore) -> None:
    pmid = f"T{uuid.uuid4().int % 10_000_000}"
    paper = Paper(dedup_key=f"pmid:{pmid}", source="pubmed", sources=["pubmed"],
                  pmid=pmid, title="Repeat study",
                  authors=[], abstract="A concise abstract about one finding.",
                  journal="Lancet")
    db.add(paper)
    await db.flush()

    first = await ingest_paper(db, paper, store)
    second = await ingest_paper(db, paper, store)  # re-ingest same paper

    assert first >= 1
    assert second == 0  # short-circuited, no duplicates
    rows = (await db.execute(select(PaperChunk).where(PaperChunk.paper_id == paper.id))).scalars().all()
    assert len(rows) == first


async def test_retrieval_finds_relevant_chunk(db: AsyncSession, store: VectorStore) -> None:
    from app.services import embeddings

    pmid = f"T{uuid.uuid4().int % 10_000_000}"
    paper = Paper(dedup_key=f"pmid:{pmid}", source="pubmed", sources=["pubmed"],
                  pmid=pmid, title="Diabetes and metformin",
                  authors=[], journal="Diabetes Care",
                  abstract="Metformin lowers blood glucose by reducing hepatic gluconeogenesis. "
                           "Separately, aspirin is used for cardiovascular prophylaxis.")
    db.add(paper)
    await db.flush()
    await ingest_paper(db, paper, store)

    qvec = await embeddings.embed_query("How does metformin control blood sugar?")
    hits = store.query(qvec, top_k=3)

    assert hits
    assert hits[0].score > 0.2
    assert "metformin" in hits[0].text.lower()
