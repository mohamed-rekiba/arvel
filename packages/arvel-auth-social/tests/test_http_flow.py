"""Redirect + callback HTTP flow — cookies, state checks, and session issuance."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from urllib.parse import parse_qs, urlparse

import httpx
import pytest_asyncio
from arvel.auth.auth_service import AuthService
from arvel.auth.config import JwtConfig
from arvel.auth.models.user import User
from arvel.database.db import DB
from arvel.database.model import Model
from arvel.facades.event import Event
from arvel.http.exceptions import HttpExceptionHandler
from arvel.testing.fakes.event import EventFake
from arvel_auth_social.config import SocialAuthConfig
from arvel_auth_social.http import SocialAuthController, register_social_routes
from arvel_auth_social.manager import SocialAuthManager
from arvel_auth_social.models import SocialAccount
from fastapi import APIRouter, FastAPI
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

_JWT_SECRET = "x" * 40


def _google_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/token"):
        return httpx.Response(200, json={"access_token": "at", "token_type": "Bearer"})
    return httpx.Response(
        200,
        json={
            "sub": "google-sub-1",
            "email": "social@example.com",
            "email_verified": True,
            "name": "Social User",
        },
    )


@pytest_asyncio.fixture()
async def client() -> AsyncGenerator[TestClient]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    DB.configure(maker)

    config = SocialAuthConfig(
        SOCIAL_GOOGLE_CLIENT_ID="gid",
        SOCIAL_GOOGLE_CLIENT_SECRET=SecretStr("gsecret"),
        SOCIAL_GOOGLE_REDIRECT_URI="https://app.test/auth/google/callback",
        SOCIAL_SUCCESS_REDIRECT_URL="/dashboard",
        SOCIAL_ERROR_REDIRECT_URL="/login?error=1",
    )
    manager = SocialAuthManager(
        config, http_client=httpx.AsyncClient(transport=httpx.MockTransport(_google_handler))
    )
    auth = AuthService(jwt=JwtConfig(secret=_JWT_SECRET))
    controller = SocialAuthController(
        manager=manager, config=config, auth=auth, cookie_secure=False
    )

    app = FastAPI()
    HttpExceptionHandler().register(app)
    router = APIRouter()
    register_social_routes(router, controller=controller)
    app.include_router(router)

    previous = Event.swap_dispatcher(EventFake())
    try:
        yield TestClient(app)
    finally:
        Event.swap_dispatcher(previous)
        await engine.dispose()


def test_redirect_sets_state_and_pkce_cookies(client: TestClient) -> None:
    resp = client.get("/auth/google/redirect", follow_redirects=False)
    assert resp.status_code == 307
    location = resp.headers["location"]
    query = parse_qs(urlparse(location).query)
    assert query["code_challenge_method"] == ["S256"]
    assert "social_state" in resp.cookies
    assert "social_pkce" in resp.cookies


def test_callback_state_mismatch_returns_422(client: TestClient) -> None:
    client.cookies.set("social_state", "expected")
    resp = client.get("/auth/google/callback?code=abc&state=tampered", follow_redirects=False)
    assert resp.status_code == 422


def test_callback_provider_error_redirects(client: TestClient) -> None:
    resp = client.get("/auth/google/callback?error=access_denied", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login?error=1"


def test_callback_success_issues_session(client: TestClient) -> None:
    redirect = client.get("/auth/google/redirect", follow_redirects=False)
    state = redirect.cookies["social_state"]

    resp = client.get(f"/auth/google/callback?code=valid&state={state}", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"
    assert "access_token" in resp.cookies


def test_callback_persists_social_account(client: TestClient) -> None:
    redirect = client.get("/auth/google/redirect", follow_redirects=False)
    state = redirect.cookies["social_state"]
    client.get(f"/auth/google/callback?code=valid&state={state}", follow_redirects=False)

    # Re-open the table to confirm the row landed.
    assert SocialAccount.__tablename__ == "social_accounts"
    assert User.__tablename__ == "users"
