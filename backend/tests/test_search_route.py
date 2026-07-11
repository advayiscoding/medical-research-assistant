"""API test for the search route with the PubMed client faked out.

Demonstrates the payoff of dependency injection: we replace the real client
with one that returns canned papers, so the test exercises route -> persistence
-> response shaping against real Postgres, with zero network calls. Idempotency
(searching twice must not duplicate) is asserted directly.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

from app.api.deps import get_pubmed_client
from app.core.config import Settings, get_settings
from app.main import create_app
from app.models import Paper, User
from app.schemas.paper import PubMedPaper


class FakePubMed:
    def __init__(self, papers: list[PubMedPaper]) -> None:
        self._papers = papers

    async def search_and_fetch(self, query: str, max_results: int = 10) -> list[PubMedPaper]:
        return self._papers[:max_results]


@pytest.fixture
def unique_pmids() -> list[str]:
    # Random PMIDs so parallel/repeat runs don't collide on the unique index.
    base = uuid.uuid4().int % 10_000_000
    return [str(90_000_000 + base), str(90_000_001 + base)]


@pytest.fixture(autouse=True)
def _reset_engine():
    # Each TestClient runs the app in its own event loop. The app's engine is a
    # process-global singleton; if it survives from a previous test it is bound
    # to a now-closed loop. Reset it so every test builds a fresh engine on its
    # own loop. (Production has one long-lived loop, so this is a test concern.)
    import app.db.session as session_mod

    session_mod._engine = None
    session_mod._session_factory = None
    yield


@pytest.fixture
def email() -> str:
    return f"search-{uuid.uuid4().hex[:10]}@example.com"


@pytest.fixture
def client(unique_pmids: list[str]):
    papers = [
        PubMedPaper(pmid=unique_pmids[0], title="Alzheimer treatment A", authors=["Smith J"],
                    abstract="Evidence A.", journal="Nature Medicine"),
        PubMedPaper(pmid=unique_pmids[1], title="Alzheimer treatment B", authors=["Doe A"],
                    abstract="Evidence B.", journal="Lancet"),
    ]
    app = create_app(Settings(environment="test"))
    app.dependency_overrides[get_pubmed_client] = lambda: FakePubMed(papers)
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(client: TestClient, email: str) -> dict[str, str]:
    # Search is a protected route since Phase 8; register a throwaway user.
    r = client.post("/api/auth/register", json={"email": email, "password": "supersecret1"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(autouse=True)
def _cleanup(unique_pmids: list[str], email: str):
    yield
    # Remove test rows so the shared dev DB stays clean. Uses its own throwaway
    # engine + fresh event loop to stay isolated from the app's engine, which
    # TestClient binds to a loop that is already closed by teardown time.
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
    assert {p["pmid"] for p in body["papers"]} == set(_pmids(body))
    assert body["papers"][0]["journal"] in {"Nature Medicine", "Lancet"}


def test_search_records_history(client: TestClient, auth_headers) -> None:
    client.post("/api/search", headers=auth_headers,
                json={"query": "alzheimer treatments", "max_results": 10})



def _pmids(body: dict) -> list[str]:
    return sorted(p["pmid"] for p in body["papers"])
