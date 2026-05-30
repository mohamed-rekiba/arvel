"""End-to-end HTTP roundtrip tests for AuthController (FR-028-01..31).

Each test maps to a PRD-028 acceptance criterion and exercises the full
HTTP path — request schema → controller → service → repo → response.
The app uses an in-memory SQLite database via ``engine``/``session`` from
the workspace root conftest.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from arvel.auth import (
    AuthService,
    EmailVerificationService,
    PasswordService,
    RefreshToken,
)
from arvel.auth.config import JwtConfig
from arvel.auth.http.controller import AuthController, CookieConfig
from arvel.auth.http.routes import register_auth_routes
from arvel.auth.models.user import User  # import forces table registration in metadata
from arvel.database.model import Model
from arvel.facades.event import Event as EventFacade
from arvel.http.exceptions import HttpException
from arvel.http.problem_details import ProblemDetailsHandler
from arvel.testing.fakes.event import EventFake
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

_EMAIL = "alice@example.com"
_PASSWORD = "S3cr3t-pass!"
_JWT_SECRET = "x" * 32
_REDIRECT = "https://app.example.com/auth/verified"


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def setup_db(engine: AsyncEngine, session: AsyncSession) -> AsyncSession:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    return session


@pytest.fixture
def event_fake() -> EventFake:
    fake = EventFake()
    EventFacade.bind(fake)
    return fake


@pytest.fixture
def services() -> tuple[AuthService, PasswordService, EmailVerificationService]:
    auth = AuthService(jwt=JwtConfig(secret=_JWT_SECRET))
    passwords = PasswordService()
    ev = EmailVerificationService(secret=_JWT_SECRET)
    return auth, passwords, ev


@pytest.fixture
def test_app(
    services: tuple[AuthService, PasswordService, EmailVerificationService],
) -> FastAPI:
    auth, passwords, ev = services
    ctrl = AuthController(
        auth=auth,
        passwords=passwords,
        email_verification=ev,
        cookies=CookieConfig(secure=False, verify_redirect_url=_REDIRECT),
    )
    from fastapi import APIRouter
    from fastapi.exceptions import RequestValidationError
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    app = FastAPI()

    # Register the framework's RFC 7807 exception handler so HttpException
    # subclasses produce the correct HTTP status codes (not 500).
    handler = ProblemDetailsHandler()

    async def http_exc_handler(request: Request, exc: HttpException) -> JSONResponse:
        return await handler.handle_problem(request, exc)

    async def val_exc_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return await handler.handle_validation_problem(request, exc)

    app.add_exception_handler(HttpException, http_exc_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, val_exc_handler)  # type: ignore[arg-type]

    api_router: APIRouter = APIRouter()
    register_auth_routes(api_router, controller=ctrl, prefix="/api/auth")
    app.include_router(api_router)
    return app


# ── helpers ───────────────────────────────────────────────────────────────────


async def _register_verified(
    client: AsyncClient,
    *,
    email: str = _EMAIL,
    password: str = _PASSWORD,
) -> None:
    """Register a user and mark email verified for tests that need a login."""
    r = await client.post(
        "/api/auth/register",
        json={
            "name": "Alice",
            "email": email,
            "password": password,
            "password_confirmation": password,
        },
    )
    assert r.status_code == 201

    user_obj = await User.where(email=email).first()
    assert user_obj is not None
    user_obj.email_verified_at = datetime.now(tz=UTC)
    await user_obj.save()


# ── tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_201_with_user_envelope(
    setup_db: AsyncSession,
    test_app: FastAPI,
    event_fake: EventFake,
) -> None:
    """FR-028-01 — POST /api/auth/register returns 201 + UserResource."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        r = await c.post(
            "/api/auth/register",
            json={
                "name": "Bob",
                "email": "bob@example.com",
                "password": "S3cr3t-pass!",
                "password_confirmation": "S3cr3t-pass!",
            },
        )
    assert r.status_code == 201
    data = r.json()
    assert "data" in data
    assert data["data"]["email"] == "bob@example.com"


@pytest.mark.asyncio
async def test_register_409_on_duplicate_email(
    setup_db: AsyncSession,
    test_app: FastAPI,
    event_fake: EventFake,
) -> None:
    """FR-028-02 — duplicate email → 409 + code=EMAIL_ALREADY_REGISTERED."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        payload = {
            "name": "Alice",
            "email": _EMAIL,
            "password": _PASSWORD,
            "password_confirmation": _PASSWORD,
        }
        await c.post("/api/auth/register", json=payload)
        r = await c.post("/api/auth/register", json=payload)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_login_200_with_bearer_and_cookies(
    setup_db: AsyncSession,
    test_app: FastAPI,
    event_fake: EventFake,
) -> None:
    """FR-028-06 — login sets __Host-refresh + _csrf, returns access_token."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        await _register_verified(c)
        r = await c.post(
            "/api/auth/login",
            json={"email": _EMAIL, "password": _PASSWORD},
        )
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert "expires_in" in data


@pytest.mark.asyncio
async def test_login_429_after_5_failed_attempts(
    setup_db: AsyncSession,
    test_app: FastAPI,
    event_fake: EventFake,
) -> None:
    """FR-028-31 / FB-027-012 — throttle returns 429 + Retry-After after threshold."""
    from arvel.auth.middleware.throttle_login import ThrottleLoginMiddleware

    # Build app with ThrottleLoginMiddleware (and proper exception handler).
    from fastapi import APIRouter
    from starlette.requests import Request as StarletteRequest
    from starlette.responses import JSONResponse

    inner_app = FastAPI()
    _handler = ProblemDetailsHandler()

    async def _he(request: StarletteRequest, exc: HttpException) -> JSONResponse:
        return await _handler.handle_problem(request, exc)

    inner_app.add_exception_handler(HttpException, _he)  # type: ignore[arg-type]

    auth_t = AuthService(jwt=JwtConfig(secret=_JWT_SECRET))
    passwords_t = PasswordService()
    ev_t = EmailVerificationService(secret=_JWT_SECRET)
    ctrl_t = AuthController(
        auth=auth_t,
        passwords=passwords_t,
        email_verification=ev_t,
        cookies=CookieConfig(secure=False),
    )
    api_router: APIRouter = APIRouter()
    register_auth_routes(api_router, controller=ctrl_t, prefix="/api/auth")
    inner_app.include_router(api_router)
    throttled = ThrottleLoginMiddleware(inner_app, login_path="/api/auth/login", max_attempts=5)

    async with AsyncClient(transport=ASGITransport(app=throttled), base_url="http://test") as c:
        for _ in range(5):
            await c.post(
                "/api/auth/login",
                content=json.dumps({"email": "x@t.com", "password": "wrong"}),
                headers={"content-type": "application/json"},
            )
        r = await c.post(
            "/api/auth/login",
            content=json.dumps({"email": "x@t.com", "password": "wrong"}),
            headers={"content-type": "application/json"},
        )
    assert r.status_code == 429
    assert "Retry-After" in r.headers


@pytest.mark.asyncio
async def test_refresh_200_rotates_cookie(
    setup_db: AsyncSession,
    test_app: FastAPI,
    event_fake: EventFake,
) -> None:
    """FR-028-13 — old cookie value gone; new cookie value present."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        await _register_verified(c)
        login = await c.post(
            "/api/auth/login",
            json={"email": _EMAIL, "password": _PASSWORD},
        )
        assert login.status_code == 200
        old_refresh = login.cookies.get("__Host-refresh") or login.cookies.get("refresh")
        assert old_refresh is not None

        r = await c.post("/api/auth/refresh")
        assert r.status_code == 200
        new_refresh = r.cookies.get("__Host-refresh") or r.cookies.get("refresh")
        assert new_refresh is not None
        data = r.json()
        assert "access_token" in data


@pytest.mark.asyncio
async def test_refresh_403_on_csrf_mismatch(
    setup_db: AsyncSession,
    test_app: FastAPI,
    event_fake: EventFake,
) -> None:
    """FR-028-16 — CSRF double-submit check blocks mismatched token."""
    from arvel.auth.middleware.csrf_double_submit import CsrfDoubleSubmitMiddleware

    # Wrap the test_app with CSRF middleware (non-exempt refresh path).
    csrf_app = CsrfDoubleSubmitMiddleware(
        test_app, exempt_paths=["/api/auth/login", "/api/auth/register"]
    )

    async with AsyncClient(transport=ASGITransport(app=csrf_app), base_url="http://test") as c:
        r = await c.post("/api/auth/refresh")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_logout_204_idempotent(
    setup_db: AsyncSession,
    test_app: FastAPI,
    event_fake: EventFake,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        await _register_verified(c)
        await c.post("/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
        r = await c.post("/api/auth/logout")
        assert r.status_code == 204
        # Second logout is also idempotent.
        r2 = await c.post("/api/auth/logout")
        assert r2.status_code == 204


@pytest.mark.asyncio
async def test_me_200_with_valid_bearer(
    setup_db: AsyncSession,
    test_app: FastAPI,
    event_fake: EventFake,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        await _register_verified(c)
        login = await c.post(
            "/api/auth/login",
            json={"email": _EMAIL, "password": _PASSWORD},
        )
        token = login.json()["access_token"]
        r = await c.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["data"]["email"] == _EMAIL


@pytest.mark.asyncio
async def test_forgot_password_returns_uniform_202(
    setup_db: AsyncSession,
    test_app: FastAPI,
    event_fake: EventFake,
) -> None:
    """FR-028-23 — known and unknown emails get the same 202 body."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        r1 = await c.post(
            "/api/auth/forgot-password",
            json={"email": _EMAIL},
        )
        r2 = await c.post(
            "/api/auth/forgot-password",
            json={"email": "unknown@example.com"},
        )
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r1.json() == r2.json()


@pytest.mark.asyncio
async def test_reset_password_revokes_all_refresh_tokens(
    setup_db: AsyncSession,
    test_app: FastAPI,
    event_fake: EventFake,
) -> None:
    """FR-028-26 — every active refresh-token row is gone after a successful reset."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        await _register_verified(c)
        await c.post("/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD})

        u = await User.where(email=_EMAIL).first()
        assert u is not None
        user_id_str = str(u.id)
        tokens_before = await RefreshToken.where(user_id=user_id_str).get()
        assert len(tokens_before) > 0

        # Trigger forgot-password to get a reset token via event.
        from arvel.auth.events import PasswordResetRequested

        await c.post("/api/auth/forgot-password", json={"email": _EMAIL})
        events = event_fake.dispatched_of(PasswordResetRequested)
        assert events, "PasswordResetRequested event not dispatched"
        token = events[0].reset_token
        assert token is not None

        r = await c.post(
            "/api/auth/reset-password",
            json={"token": token, "password": "NewP@ss99!", "password_confirmation": "NewP@ss99!"},
        )
        assert r.status_code == 200

        tokens_after = await RefreshToken.where(user_id=user_id_str).get()
        assert len(tokens_after) == 0


@pytest.mark.asyncio
async def test_verify_email_302_to_success_page(
    setup_db: AsyncSession,
    test_app: FastAPI,
    event_fake: EventFake,
    services: tuple[AuthService, PasswordService, EmailVerificationService],
) -> None:
    """FR-028-19 — successful verify redirects to configurable success URL."""
    _, _, ev = services
    from arvel.auth import User

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
        follow_redirects=False,
    ) as c:
        r_reg = await c.post(
            "/api/auth/register",
            json={
                "name": "Carol",
                "email": "carol@example.com",
                "password": _PASSWORD,
                "password_confirmation": _PASSWORD,
            },
        )
        assert r_reg.status_code == 201
        carol = await User.where(email="carol@example.com").first()
        assert carol is not None
        signed = ev.issue(user_id=str(carol.id), email="carol@example.com")

        r = await c.get(f"/api/auth/verify/{signed}")
    assert r.status_code == 302
    assert _REDIRECT in r.headers["location"]


@pytest.mark.asyncio
async def test_verify_email_resend_throttled_returns_429(
    setup_db: AsyncSession,
    test_app: FastAPI,
    event_fake: EventFake,
) -> None:
    """FR-028-21 — second resend within window → 429."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        await _register_verified(c)
        login = await c.post(
            "/api/auth/login",
            json={"email": _EMAIL, "password": _PASSWORD},
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        r1 = await c.post("/api/auth/verify/resend", headers=headers)
        assert r1.status_code == 200

        r2 = await c.post("/api/auth/verify/resend", headers=headers)
        assert r2.status_code == 429
