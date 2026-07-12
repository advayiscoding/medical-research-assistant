"""Federated search: query all sources in parallel, dedup, merge, rank.

This is the orchestration the feature is really about. Four steps:

1. FAN-OUT (parallel). All ten providers run concurrently via asyncio.gather.
   Each is wrapped so one source failing (timeout, 429, schema change) yields an
   empty list instead of taking down the whole search — partial results beat no
   results. A per-source timeout bounds the slowest source.

2. DEDUP + MERGE. The same paper often appears in 3-5 sources (PubMed + OpenAlex
   + Crossref + Europe PMC all index the same DOI). We group by canonical
   dedup_key and merge into one record: union the source list, keep the max
   citation count, and prefer the longest abstract / richest metadata. Provenance
   (every source that returned it) is preserved on the merged record.

3. RANK. We fuse the per-source relevance rankings with Reciprocal Rank Fusion
   (RRF) — the standard, tuning-free way to combine heterogeneous ranked lists —
   then add a citation bonus. A paper ranked highly by several sources AND
   heavily cited rises to the top; neither signal alone dominates.

4. Return the ranked, merged records for persistence + ingestion.
"""

import asyncio
import logging
import math
from dataclasses import dataclass, field

from app.services.sources.base import SourceProvider, SourceRecord

logger = logging.getLogger(__name__)

PER_SOURCE_TIMEOUT = 20.0  # seconds; a slow source can't stall the whole search
RRF_K = 60  # RRF dampening constant (standard default)
CITATION_WEIGHT = 0.15  # how much citation count nudges the fused relevance score


@dataclass
class MergedRecord:
    """A deduplicated record plus the provenance and score the ranking produced."""

    record: SourceRecord
    sources: list[str] = field(default_factory=list)
    score: float = 0.0


async def _run_provider(provider: SourceProvider, query: str, limit: int) -> list[SourceRecord]:
    """Isolate one source: timeout-bounded, never raises. A failure just means
    that source contributes nothing to this search."""
    try:
        async with asyncio.timeout(PER_SOURCE_TIMEOUT):
            records = await provider.search(query, limit)
        logger.info("source %s -> %d records", provider.name, len(records))
        return records
    except Exception as exc:  # noqa: BLE001 - deliberate: isolate one source's failure
        logger.warning("source %s failed: %s: %s", provider.name, type(exc).__name__, exc)
        return []


async def federated_search(
    providers: list[SourceProvider],
    query: str,
    per_source_limit: int = 10,
    final_limit: int = 20,
) -> list[MergedRecord]:
    # 1. FAN-OUT
    results = await asyncio.gather(
        *(_run_provider(p, query, per_source_limit) for p in providers)
    )

    # 2. DEDUP + MERGE, while remembering each source's rank of each key for RRF.
    merged: dict[str, MergedRecord] = {}
    ranks_by_key: dict[str, list[int]] = {}
    for source_records in results:
        for rec in source_records:
            key = rec.dedup_key()
            ranks_by_key.setdefault(key, []).append(rec.rank)
            if key not in merged:
                merged[key] = MergedRecord(record=rec, sources=[rec.source])
            else:
                _merge_into(merged[key], rec)

    # 3. RANK: RRF over per-source ranks + citation bonus.
    for key, mr in merged.items():
        rrf = sum(1.0 / (RRF_K + rank + 1) for rank in ranks_by_key[key])
        citation_bonus = CITATION_WEIGHT * math.log1p(mr.record.citation_count)
        # Cross-source agreement is itself a relevance signal: a paper found by
        # many sources is likely on-topic. RRF already rewards this (more terms
        # in the sum), and we keep it visible via len(sources).
        mr.score = rrf + citation_bonus

    ranked = sorted(merged.values(), key=lambda m: m.score, reverse=True)
    logger.info(
        "federated_search %r: %d raw -> %d unique (top score %.4f)",
        query, sum(len(r) for r in results), len(ranked),
        ranked[0].score if ranked else 0.0,
    )
    return ranked[:final_limit]


def _merge_into(target: MergedRecord, other: SourceRecord) -> None:
    """Fold a duplicate from another source into the kept record. Keep the best
    of each field; never lose provenance."""
    if other.source not in target.sources:
        target.sources.append(other.source)
    kept = target.record

    # Max citation count — different sources report different (stale) counts.
    kept.citation_count = max(kept.citation_count, other.citation_count)
    # Prefer the longer abstract (usually the more complete one).
    if other.abstract and len(other.abstract) > len(kept.abstract or ""):
        kept.abstract = other.abstract
    # Backfill identifiers we didn't have yet.
    kept.doi = kept.doi or other.doi
    kept.pmid = kept.pmid or other.pmid
    kept.journal = kept.journal or other.journal
    kept.publication_date = kept.publication_date or other.publication_date
    kept.url = kept.url or other.url
    if len(other.authors) > len(kept.authors):
        kept.authors = other.authors
