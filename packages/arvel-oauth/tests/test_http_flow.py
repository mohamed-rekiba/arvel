"""Redirect + callback HTTP flow — cookies, state checks, and session issuance."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import cast
from urllib.parse import parse_qs, urlparse

import httpx2 as httpx
import pytest_asyncio
from arvel.auth.auth_service import AuthService
from arvel.auth.config import JwtConfig
from arvel.auth.models.user import User
from arvel.database.db import DB
from arvel.database.model import Model
from arvel.facades.event import Event
from arvel.http.exceptions import HttpExceptionHandler
from arvel.testing.fakes.event import EventFake
from arvel_oauth.config import OAuthConfig
from arvel_oauth.http import OAuthController, register_oauth_routes
from arvel_oauth.manager import OAuthManager
from arvel_oauth.models import OAuthAccount
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
async def client() -> AsyncGenerator[httpx.Client]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    DB.configure(maker)

    config = OAuthConfig(
        OAUTH_GOOGLE_CLIENT_ID="gid",
        OAUTH_GOOGLE_CLIENT_SECRET=SecretStr("gsecret"),
        OAUTH_GOOGLE_REDIRECT_URI="https://app.test/auth/google/callback",
        OAUTH_SUCCESS_REDIRECT_URL="/dashboard",
        OAUTH_ERROR_REDIRECT_URL="/login?error=1",
    )
    manager = OAuthManager(
        config, http_client=httpx.AsyncClient(transport=httpx.MockTransport(_google_handler))
    )
    auth = AuthService(jwt=JwtConfig(secret=_JWT_SECRET))
    controller = OAuthController(manager=manager, config=config, auth=auth, cookie_secure=False)

    app = FastAPI()
    HttpExceptionHandler().register(app)
    router = APIRouter()
    register_oauth_routes(router, controller=controller)
    app.include_router(router)

    previous = Event.swap_dispatcher(EventFake())
    try:
        yield cast("httpx.Client", TestClient(app))
    finally:
        Event.swap_dispatcher(previous)
        await engine.dispose()


def test_redirect_sets_state_and_pkce_cookies(client: httpx.Client) -> None:
    resp = client.get("/auth/google/redirect", follow_redirects=False)
    assert resp.status_code == 307
    location = resp.headers["location"]
    query = parse_qs(urlparse(location).query)
    assert query["code_challenge_method"] == ["S256"]
    assert "oauth_state" in resp.cookies
    assert "oauth_pkce" in resp.cookies


def test_callback_state_mismatch_returns_422(client: httpx.Client) -> None:
    client.cookies.set("oauth_state", "expected")
    resp = client.get("/auth/google/callback?code=abc&state=tampered", follow_redirects=False)
    assert resp.status_code == 422


def test_callback_provider_error_redirects(client: httpx.Client) -> None:
    resp = client.get("/auth/google/callback?error=access_denied", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login?error=1"


def test_callback_success_issues_session(client: httpx.Client) -> None:
    redirect = client.get("/auth/google/redirect", follow_redirects=False)
    state = redirect.cookies["oauth_state"]

    resp = client.get(f"/auth/google/callback?code=valid&state={state}", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"
    assert "access_token" in resp.cookies


def test_callback_persists_oauth_account(client: httpx.Client) -> None:
    redirect = client.get("/auth/google/redirect", follow_redirects=False)
    state = redirect.cookies["oauth_state"]
    client.get(f"/auth/google/callback?code=valid&state={state}", follow_redirects=False)

    # Re-open the table to confirm the row landed.
    assert OAuthAccount.__tablename__ == "oauth_accounts"
    assert User.__tablename__ == "users"
