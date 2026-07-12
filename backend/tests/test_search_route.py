"""API test for the federated search route with the source providers faked out.

Demonstrates the payoff of dependency injection: we replace the ten live
providers with one fake returning canned SourceRecords, so the test exercises
route -> federation -> persistence -> response shaping against real Postgres,
with zero network calls. Idempotency (searching twice must not duplicate) and
provenance (source badges) are asserted directly.
"""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import create_async_engine

from app.api.deps import get_source_providers
from app.core.config import Settings, get_settings
from app.main import create_app
from app.models import Paper, User
from app.services.sources.base import SourceRecord


class FakeProvider:
    """Stands in for a real source provider; returns canned records."""

    def __init__(self, name: str, records: list[SourceRecord]) -> None:
        self.name = name
        self._records = records

    async def search(self, query: str, limit: int) -> list[SourceRecord]:
        return self._records[:limit]


@pytest.fixture
def unique_pmids() -> list[str]:
    base = uuid.uuid4().int % 10_000_000
    return [str(90_000_000 + base), str(90_000_001 + base)]


@pytest.fixture(autouse=True)
def _reset_engine():
    import app.db.session as session_mod

    session_mod._engine = None
    session_mod._session_factory = None
    yield


@pytest.fixture
def email() -> str:
    return f"search-{uuid.uuid4().hex[:10]}@example.com"


@pytest.fixture
def client(unique_pmids: list[str]):
    # Two records from different sources; one carries a citation count so we can
    # assert citation-aware ranking flows through to the response.
    records = [
        SourceRecord(source="pubmed", pmid=unique_pmids[0], title="Alzheimer treatment A",
                     authors=["Smith J"], abstract="Evidence A.", journal="Nature Medicine",
                     citation_count=500, rank=0),
        SourceRecord(source="openalex", pmid=unique_pmids[1], title="Alzheimer treatment B",
                     authors=["Doe A"], abstract="Evidence B.", journal="Lancet", rank=1),
    ]
    app = create_app(Settings(environment="test"))
    app.dependency_overrides[get_source_providers] = lambda: [
        FakeProvider("pubmed", [records[0]]),
        FakeProvider("openalex", [records[1]]),
    ]
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(client: TestClient, email: str) -> dict[str, str]:
    r = client.post("/api/auth/register", json={"email": email, "password": "supersecret1"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(autouse=True)
def _cleanup(unique_pmids: list[str], email: str):
    yield

    async def _del() -> None:
        engine = create_async_engine(get_settings().database_url)
        async with engine.begin() as conn:
            await conn.execute(delete(Paper).where(Paper.pmid.in_(unique_pmids)))
            await conn.execute(delete(User).where(User.email == email))
        await engine.dispose()

    asyncio.run(_del())


def test_search_requires_auth(client: TestClient) -> None:
    resp = client.post("/api/search", json={"query": "alzheimer", "max_results": 5})
    assert resp.status_code == 401


def test_search_persists_and_returns_papers(client: TestClient, auth_headers) -> None:
    resp = client.post("/api/search", headers=auth_headers,
                       json={"query": "alzheimer treatments", "max_results": 10})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    # Provenance flows through: each paper names its source.
    sources = {p["source"] for p in body["papers"]}
    assert sources == {"pubmed", "openalex"}
    # Citation-aware ranking: the 500-citation paper ranks first.
    assert body["papers"][0]["citation_count"] == 500


def test_search_is_idempotent(client: TestClient, auth_headers) -> None:
    first = client.post("/api/search", headers=auth_headers,
                        json={"query": "alzheimer", "max_results": 10}).json()
    second = client.post("/api/search", headers=auth_headers,
                         json={"query": "alzheimer", "max_results": 10}).json()
    assert first["count"] == second["count"] == 2
    assert _pmids(first) == _pmids(second)


def _pmids(body: dict) -> list[str]:
    return sorted(p["pmid"] for p in body["papers"])
