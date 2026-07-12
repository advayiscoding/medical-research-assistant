"""Unit tests for the federation algorithm — dedup, merge, ranking (no network).

Uses fake providers returning hand-built SourceRecords so the merge and RRF +
citation ranking are asserted deterministically, independent of live APIs.
"""

import pytest

from app.services.federation import federated_search
from app.services.sources.base import SourceRecord

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeProvider:
    def __init__(self, name: str, records: list[SourceRecord]) -> None:
        self.name = name
        self._records = records

    async def search(self, query: str, limit: int) -> list[SourceRecord]:
        return self._records[:limit]


class BrokenProvider:
    name = "broken"

    async def search(self, query: str, limit: int) -> list[SourceRecord]:
        raise RuntimeError("simulated source outage")


def _rec(source, rank, *, doi=None, pmid=None, cites=0, title="X", abstract="a"):
    return SourceRecord(source=source, title=title, abstract=abstract, doi=doi,
                        pmid=pmid, citation_count=cites, rank=rank)


async def test_dedup_merges_same_doi_across_sources() -> None:
    # Same DOI from three sources → one merged record naming all three.
    providers = [
        FakeProvider("pubmed", [_rec("pubmed", 0, doi="10.1/x", pmid="111")]),
        FakeProvider("openalex", [_rec("openalex", 0, doi="10.1/X", cites=900)]),  # case-insensitive
        FakeProvider("crossref", [_rec("crossref", 0, doi="https://doi.org/10.1/x")]),
    ]
    merged = await federated_search(providers, "q", per_source_limit=5, final_limit=10)

    assert len(merged) == 1
    m = merged[0]
    assert set(m.sources) == {"pubmed", "openalex", "crossref"}
    assert m.record.citation_count == 900  # max across sources
    assert m.record.pmid == "111"  # backfilled from the source that had it


async def test_ranking_prefers_citations_when_relevance_ties() -> None:
    # Two distinct papers, both rank 0 in their source; the more-cited wins.
    providers = [
        FakeProvider("a", [_rec("a", 0, doi="10.1/low", cites=1, title="Low")]),
        FakeProvider("b", [_rec("b", 0, doi="10.1/high", cites=5000, title="High")]),
    ]
    merged = await federated_search(providers, "q", final_limit=10)
    assert merged[0].record.title == "High"


async def test_cross_source_agreement_outranks_single_source() -> None:
    # A paper found by 3 sources (rank 1 each) beats a single-source rank-0 paper:
    # RRF rewards agreement across sources.
    providers = [
        FakeProvider("a", [_rec("a", 0, doi="10.1/solo", title="Solo"),
                           _rec("a", 1, doi="10.1/agreed", title="Agreed")]),
        FakeProvider("b", [_rec("b", 1, doi="10.1/agreed", title="Agreed")]),
        FakeProvider("c", [_rec("c", 1, doi="10.1/agreed", title="Agreed")]),
    ]
    merged = await federated_search(providers, "q", final_limit=10)
    assert merged[0].record.title == "Agreed"
    assert len(merged[0].sources) == 3


async def test_one_source_failure_does_not_break_search() -> None:
    # A broken source is isolated; the others still return results.
    providers = [
        BrokenProvider(),
        FakeProvider("ok", [_rec("ok", 0, doi="10.1/ok", title="Survivor")]),
    ]
    merged = await federated_search(providers, "q", final_limit=10)
    assert [m.record.title for m in merged] == ["Survivor"]


async def test_merge_keeps_longest_abstract() -> None:
    providers = [
        FakeProvider("a", [_rec("a", 0, pmid="222", abstract="short")]),
        FakeProvider("b", [_rec("b", 0, pmid="222", abstract="a much longer abstract with detail")]),
    ]
    merged = await federated_search(providers, "q", final_limit=10)
    assert merged[0].record.abstract == "a much longer abstract with detail"
