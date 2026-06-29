"""The ``signed`` route middleware (ValidateSignature): a route protected by it 403s unless the
request URL carries a valid (and unexpired) signature from ``Router.signed_url``. The signing key
defaults to the app key.
"""

from __future__ import annotations

import time
from typing import Any

from litestar.testing import TestClient

from arvel import Application, Route
from arvel.http.middleware import ValidateSignature
from arvel.kernel import set_application
from arvel.kernel.bootstrap import bootstrap_app


async def _handler(request: Any) -> dict[str, bool]:
    return {"ok": True}


def _app() -> Application:
    app = (
        Application.configure(".")
        .with_config({"app": {"key": "base64:" + "A" * 43 + "=", "url": "http://test"}})
        .create()
    )
    bootstrap_app(app)  # binds the router
    Route.get("/unsub", _handler, name="unsub").middleware(ValidateSignature)
    return app


def test_signed_middleware_allows_valid_and_rejects_tampered_or_expired() -> None:
    app = _app()
    try:
        router = app.make("router")
        signed = router.signed_url("unsub")  # key defaults to the app key
        with TestClient(app=app.as_asgi()) as client:
            # a valid signature passes
            assert client.get(signed).status_code == 200
            # no signature → 403
            assert client.get("/unsub").status_code == 403
            # a tampered signature → 403
            assert client.get(signed + "tamper").status_code == 403
            # an already-expired temporary URL → 403
            expired = router.signed_url("unsub", expires=int(time.time()) - 60)
            assert client.get(expired).status_code == 403
            # a future expiry is accepted
            valid_future = router.signed_url("unsub", expires=int(time.time()) + 3600)
            assert client.get(valid_future).status_code == 200
    finally:
        set_application(None)


def test_signed_url_key_defaults_to_app_key() -> None:
    app = _app()
    try:
        router = app.make("router")
        # signed_url + has_valid_signature round-trip without an explicit key= (uses config app.key)
        url = router.signed_url("unsub")
        assert router.has_valid_signature(url) is True
        assert router.has_valid_signature(url + "x") is False
    finally:
        set_application(None)
