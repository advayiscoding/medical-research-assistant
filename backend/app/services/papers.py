"""Persistence for papers — the bridge between PubMed results and Postgres.

Kept separate from the PubMed client (which only knows the API) and from the
route (which only knows HTTP). This is where "store the papers" logic lives,
and it is deliberately idempotent: searching overlapping topics must not create
duplicate rows.
"""

import logging
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Paper
from app.schemas.paper import PubMedPaper

logger = logging.getLogger(__name__)


async def upsert_papers(db: AsyncSession, papers: Sequence[PubMedPaper]) -> list[Paper]:
    """Insert papers, skipping any whose PMID already exists (ON CONFLICT DO
    NOTHING). Returns the persisted Paper rows for the given PMIDs — both the
    freshly inserted and the pre-existing — so callers get stable IDs to link
    chunks and citations against.

    Why ON CONFLICT rather than 'SELECT then INSERT missing': the check-then-act
    version has a race — two concurrent searches for the same topic can both
    pass the check and both insert, violating the unique constraint. Letting
    Postgres resolve the conflict atomically removes the race entirely.
    """
    if not papers:
        return []

    rows = [
        {
            "pmid": p.pmid,
            "title": p.title,
            "authors": p.authors,
            "abstract": p.abstract,
            "journal": p.journal,
            "publication_date": p.publication_date,
        }
        for p in papers
    ]
    stmt = pg_insert(Paper).values(rows).on_conflict_do_nothing(index_elements=["pmid"])
    await db.execute(stmt)
    await db.flush()

    pmids = [p.pmid for p in papers]
    result = await db.execute(select(Paper).where(Paper.pmid.in_(pmids)))
    persisted = list(result.scalars().all())
    logger.info("upserted %d papers (%d unique persisted)", len(papers), len(persisted))
    return persisted
