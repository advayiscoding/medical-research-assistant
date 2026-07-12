"""Persistence for federated papers — the bridge between the source federation
and Postgres.

Idempotent by `dedup_key` (the canonical cross-source identity), so re-searching
overlapping topics never duplicates a row even when the paper arrives from a
different source the second time. ON CONFLICT DO NOTHING resolves the race where
two concurrent searches insert the same paper.
"""

import logging
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Paper
from app.services.federation import MergedRecord

logger = logging.getLogger(__name__)


async def upsert_papers(db: AsyncSession, merged: Sequence[MergedRecord]) -> list[Paper]:
    """Insert merged records, skipping any whose dedup_key already exists.
    Returns the persisted Paper rows (new + pre-existing) in the same relevance
    order as `merged`, so callers can ingest/rank them consistently."""
    if not merged:
        return []

    rows = []
    for m in merged:
        r = m.record
        rows.append(
            {
                "dedup_key": r.dedup_key(),
                "source": r.source,
                "sources": m.sources,
                "pmid": r.pmid,
                "doi": r.doi,
                "external_id": r.external_id,
                "title": r.title,
                "authors": r.authors,
                "abstract": r.abstract,
                "journal": r.journal,
                "publication_date": r.publication_date,
                "citation_count": r.citation_count,
                "url": r.url,
                "is_preprint": r.is_preprint,
            }
        )
    stmt = pg_insert(Paper).values(rows).on_conflict_do_nothing(index_elements=["dedup_key"])
    await db.execute(stmt)
    await db.flush()

    # Return rows in the caller's relevance order (dict preserves insertion; we
    # map dedup_key -> Paper then re-order).
    keys = [m.record.dedup_key() for m in merged]
    result = await db.execute(select(Paper).where(Paper.dedup_key.in_(keys)))
    by_key = {p.dedup_key: p for p in result.scalars().all()}
    persisted = [by_key[k] for k in keys if k in by_key]
    logger.info("upserted %d merged records (%d persisted)", len(merged), len(persisted))
    return persisted
