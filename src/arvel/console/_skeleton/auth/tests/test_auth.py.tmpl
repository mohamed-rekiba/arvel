"""Bearer-token auth flow — login issues a token; the protected route requires it.

Seeds a user into a temporary sqlite file (via DATABASE_URL) that the served app then reads, so the
whole flow is exercised through the real HTTP path.
"""

import asyncio

import pytest
from litestar.testing import TestClient

from arvel.database import ConnectionResolver, Migrator, discover_migrations

from app.models.user import User


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Sync fixture: TestClient runs the app in its own event loop, so do the async migrate+seed via
    # asyncio.run (not an async fixture, which would start the client inside a running loop).
    url = f"sqlite+aiosqlite:///{tmp_path / 'auth.sqlite'}"
    monkeypatch.setenv("DATABASE_URL", url)

    async def migrate_and_seed() -> None:
        seed_db = ConnectionResolver({"default": {"url": url}})
        await Migrator(seed_db).run(discover_migrations(["database/migrations"]))
        User.set_connection(seed_db)
        await User.create(name="Test User", email="test@example.com", password="secret")
        User.set_connection(None)  # routes use the served app's own connection (same sqlite file)
        await seed_db.dispose()

    asyncio.run(migrate_and_seed())

    # Build a fresh app so it reads the overridden DATABASE_URL (the module-level asgi_app may already
    # be bootstrapped against the default DB from an earlier test).
    from bootstrap.app import create_app

    with TestClient(app=create_app().as_asgi()) as test_client:
        yield test_client


def test_wrong_password_is_rejected(client) -> None:
    resp = client.post("/api/login", json={"email": "test@example.com", "password": "wrong"})
    assert resp.status_code == 401


def test_login_issues_a_token_that_unlocks_the_protected_route(client) -> None:
    resp = client.post("/api/login", json={"email": "test@example.com", "password": "secret"})
    assert resp.status_code == 200
    token = resp.json()["token"]

    assert client.get("/api/user").status_code == 401  # no token -> rejected
    authed = client.get("/api/user", headers={"Authorization": f"Bearer {token}"})
    assert authed.status_code == 200
    assert authed.json()["email"] == "test@example.com"
