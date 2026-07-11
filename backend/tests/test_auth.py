"""Auth flow tests: registration, login, and route protection.

Runs against real Postgres (test env => NullPool). Each test uses a unique
email and cleans up after itself so the shared dev DB stays tidy.
"""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings, get_settings
from app.main import create_app
from app.models import User


@pytest.fixture(autouse=True)
def _reset_engine():
    import app.db.session as session_mod

    session_mod._engine = None
    session_mod._session_factory = None
    yield


@pytest.fixture
def email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


@pytest.fixture
def client():
    app = create_app(Settings(environment="test"))
    yield TestClient(app)


@pytest.fixture(autouse=True)
def _cleanup(email: str):
    yield

    async def _del() -> None:
        engine = create_async_engine(get_settings().database_url)
        async with engine.begin() as conn:
            await conn.execute(delete(User).where(User.email == email))
        await engine.dispose()

    asyncio.run(_del())


def test_register_returns_token(client: TestClient, email: str) -> None:
    resp = client.post("/api/auth/register", json={"email": email, "password": "supersecret1"})
    assert resp.status_code == 201
    assert resp.json()["access_token"]


def test_register_duplicate_rejected(client: TestClient, email: str) -> None:
    client.post("/api/auth/register", json={"email": email, "password": "supersecret1"})
    dup = client.post("/api/auth/register", json={"email": email, "password": "supersecret1"})
    assert dup.status_code == 409


def test_login_and_access_protected_route(client: TestClient, email: str) -> None:
    client.post("/api/auth/register", json={"email": email, "password": "supersecret1",
                                            "full_name": "Ada L"})
    login = client.post("/api/auth/login", json={"email": email, "password": "supersecret1"})
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email
    assert me.json()["full_name"] == "Ada L"


def test_login_wrong_password_rejected(client: TestClient, email: str) -> None:
    client.post("/api/auth/register", json={"email": email, "password": "supersecret1"})
    bad = client.post("/api/auth/login", json={"email": email, "password": "wrongpassword"})
    assert bad.status_code == 401


def test_protected_route_requires_token(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
