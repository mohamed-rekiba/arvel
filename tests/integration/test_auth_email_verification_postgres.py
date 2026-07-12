"""E13/S2 — email-bound verification links, driven through the real HTTP verify route
(``docs/auth/routes-and-flows.md#email-verification``) against real Postgres.

Proves what the ``flows.py`` unit tests can't: a link issued for a user's email is accepted by the
route while unchanged, and rejected the moment the row's email changes — the DB round-trip, not
just the in-memory hash comparison, is what invalidates it.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, ClassVar

import httpx
import pytest
import sqlalchemy as sa

from arvel import Application, Route, abort
from arvel.auth import Authenticatable
from arvel.auth.flows import email_verification_token, verify_email_token
from arvel.database import Model
from arvel.kernel import set_application
from arvel.kernel.bootstrap import bootstrap_app

pytestmark = pytest.mark.integration

SIG = "e13-s2-integration-signing-value"  # throwaway test-only value, not a real APP_KEY


class VerifyUser(Model, Authenticatable):
    __table_name__ = "verify_users"
    __fields__: ClassVar[dict[str, Any]] = {"email": str, "email_verified_at": str}
    __fillable__: ClassVar[list[str]] = ["email"]
    __casts__: ClassVar[dict[str, str]] = {"email_verified_at": "datetime"}


async def _verify(request: Any) -> Any:
    """The route from docs/auth/routes-and-flows.md#email-verification (``abort`` instead of the
    doc's prose tuple-return, matching how the rest of the codebase signals an HTTP error — see
    ``_login`` in tests/integration/test_reference_app.py)."""
    user = await VerifyUser.find(request.path_param("id"))
    if user is None:
        abort(400, "This link is invalid or expired.")
    user_id = verify_email_token(request.query("token"), user.email, SIG)
    if user_id is None or str(user_id) != str(user.id):
        abort(400, "This link is invalid or expired.")
    await user.mark_email_as_verified()
    return {"verified": True}


async def _verify_short_lived(request: Any) -> Any:
    """Same route, ``max_age=-1`` — a test-only variant proving the expiry path fires when driven
    over HTTP, without waiting out the real 60-minute TTL."""
    user = await VerifyUser.find(request.path_param("id"))
    if user is None:
        abort(400, "This link is invalid or expired.")
    user_id = verify_email_token(request.query("token"), user.email, SIG, max_age=-1)
    if user_id is None or str(user_id) != str(user.id):
        abort(400, "This link is invalid or expired.")
    return {"verified": True}


async def test_email_verification_route_rejects_after_email_change_on_postgres(
    postgres_url: str,
) -> None:
    app = (
        Application.configure(".")
        .with_config(
            {
                "app": {"key": "base64:" + "A" * 43 + "=", "url": "http://test"},
                "database": {"default": "pgsql", "connections": {"pgsql": {"url": postgres_url}}},
            }
        )
        .create()
    )
    try:
        bootstrap_app(app)
        Route.get("/email/verify/{id:int}", _verify, name="verify")
        Route.get("/email/verify-short/{id:int}", _verify_short_lived, name="verify.short")
        await app.boot()
        db = app.make("db")
        VerifyUser.set_connection(db)
        await db.execute(sa.schema.CreateTable(VerifyUser.__table__))

        alice = await VerifyUser.create(email="alice@example.com")
        bob = await VerifyUser.create(email="bob@example.com")

        transport = httpx.ASGITransport(app=app.as_asgi())
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            link = email_verification_token(alice.id, alice.email, SIG)

            # freshly issued, email unchanged -> success
            ok = await c.get(f"/email/verify/{alice.id}", params={"token": link})
            assert ok.status_code == 200 and ok.json()["verified"] is True

            # change the email IN THE DB, then replay the SAME (still-fresh) link -> rejected
            alice.email = "alice-new@example.com"
            await alice.save()
            # visibility barrier: the route reads through its own pooled connection; on slow CI
            # the replay occasionally raced the write and read the OLD email (200 instead of
            # 400 — the F-25 flake). Wait until a FRESH query sees the change before replaying.
            for _ in range(40):
                fresh = await VerifyUser.find(alice.id)
                if fresh is not None and fresh.email == "alice-new@example.com":
                    break
                await asyncio.sleep(0.05)
            else:
                raise AssertionError("email change never became visible to a fresh query")
            replay = await c.get(f"/email/verify/{alice.id}", params={"token": link})
            assert replay.status_code == 400

            # a freshly issued link for the NEW email succeeds
            fresh = email_verification_token(alice.id, alice.email, SIG)
            ok2 = await c.get(f"/email/verify/{alice.id}", params={"token": fresh})
            assert ok2.status_code == 200

            # expired (max_age=-1 route) -> rejected
            expiring = email_verification_token(alice.id, alice.email, SIG)
            expired = await c.get(f"/email/verify-short/{alice.id}", params={"token": expiring})
            assert expired.status_code == 400

            # tampered/forged token -> rejected
            forged = await c.get(f"/email/verify/{alice.id}", params={"token": fresh[:-1] + "x"})
            assert forged.status_code == 400

            # cross-user id swap: Alice's valid token presented against Bob's id — Bob's current
            # email hashes differently, so the bound hash mismatches and the route rejects it
            swapped = await c.get(f"/email/verify/{bob.id}", params={"token": fresh})
            assert swapped.status_code == 400
    finally:
        with contextlib.suppress(Exception):
            await app.make("db").dispose()
        set_application(None)
