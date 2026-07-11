"""Chat persistence tests — end to end with a fake LLM.

Real Postgres + real Chroma (temp dir) + fake Claude. Proves the whole Phase 7b
loop: register -> create session -> upload/ingest a doc -> ask -> answer is
persisted with citations -> history is retrievable -> other users can't see it.
"""

import asyncio
import io
import uuid

import pytest
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import create_async_engine

from app.api.deps import get_llm, get_store
from app.core.config import Settings, get_settings
from app.main import create_app
from app.models import User
from app.services.vector_store import VectorStore


class FakeLLM:
    """Returns an answer that cites source [1], so citation persistence has
    something real to resolve against the ingested chunk."""

    async def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> str:
        return "Metformin lowers blood glucose by reducing hepatic gluconeogenesis [1]."


@pytest.fixture(autouse=True)
def _reset_engine():
    import app.db.session as session_mod

    session_mod._engine = None
    session_mod._session_factory = None
    yield


@pytest.fixture
def emails() -> list[str]:
    return [f"u-{uuid.uuid4().hex[:10]}@example.com" for _ in range(2)]


@pytest.fixture
def client(tmp_path, emails):
    store = VectorStore(Settings(environment="test", chroma_persist_dir=str(tmp_path / "c")))
    app = create_app(Settings(environment="test"))
    app.dependency_overrides[get_llm] = lambda: FakeLLM()
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _cleanup(emails):
    yield

    async def _del() -> None:
        engine = create_async_engine(get_settings().database_url)
        async with engine.begin() as conn:
            await conn.execute(delete(User).where(User.email.in_(emails)))
        await engine.dispose()

    asyncio.run(_del())


def _pdf(text: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    y = 750
    for line in text.split("\n"):
        c.drawString(72, y, line)
        y -= 18
    c.save()
    return buf.getvalue()


def _auth(client: TestClient, email: str) -> dict[str, str]:
    r = client.post("/api/auth/register", json={"email": email, "password": "supersecret1"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_full_chat_flow_persists_answer_and_citations(client: TestClient, emails) -> None:
    h = _auth(client, emails[0])

    # Ingest a document so retrieval has real, citable evidence.
    body = ("Metformin lowers blood glucose by reducing hepatic gluconeogenesis. " * 8)
    up = client.post("/api/documents", headers=h,
                     files={"file": ("metformin.pdf", _pdf(body), "application/pdf")})
    assert up.status_code == 201, up.text
    assert up.json()["document"]["status"] == "ready"
    assert up.json()["chunks_created"] >= 1

    # Create a session and ask a question.
    sid = client.post("/api/chat/sessions", headers=h).json()["id"]
    ask = client.post(f"/api/chat/sessions/{sid}/messages", headers=h,
                      json={"question": "How does metformin control blood sugar?"})
    assert ask.status_code == 200, ask.text
    body = ask.json()
    assert body["insufficient_evidence"] is False
    assert "[1]" in body["assistant_message"]["content"]
    cites = body["assistant_message"]["citations"]
    assert len(cites) == 1
    assert cites[0]["marker"] == 1
    assert "metformin" in cites[0]["chunk"]["text"].lower()

    # History: the session detail returns both turns, with the citation intact.
    detail = client.get(f"/api/chat/sessions/{sid}", headers=h).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["title"].startswith("How does metformin")
    assert detail["messages"][1]["citations"][0]["marker"] == 1


def test_sessions_are_isolated_per_user(client: TestClient, emails) -> None:
    h1 = _auth(client, emails[0])
    h2 = _auth(client, emails[1])

    sid = client.post("/api/chat/sessions", headers=h1).json()["id"]

    # Owner sees it; the other user gets 404 (not 403 — we don't reveal existence).
    assert client.get(f"/api/chat/sessions/{sid}", headers=h1).status_code == 200
    assert client.get(f"/api/chat/sessions/{sid}", headers=h2).status_code == 404
    assert client.get("/api/chat/sessions", headers=h2).json() == []


def test_ask_without_evidence_reports_insufficient(client: TestClient, emails) -> None:
    h = _auth(client, emails[0])
    sid = client.post("/api/chat/sessions", headers=h).json()["id"]
    # No documents ingested for this user's query topic -> retrieval floor trips.
    ask = client.post(f"/api/chat/sessions/{sid}/messages", headers=h,
                      json={"question": "What is the airspeed velocity of an unladen swallow?"})
    assert ask.status_code == 200
    assert ask.json()["insufficient_evidence"] is True
    assert ask.json()["assistant_message"]["citations"] == []
