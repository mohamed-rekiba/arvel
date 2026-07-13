"""PendingRequest builders: retry, timeouts, form/multipart/attach, accept, auth (spec 07 §1)."""

from __future__ import annotations

import base64
from typing import Any

import httpx
import pytest

from arvel.client import Client, ClientResponse, RequestFailed


class _FlakyTransport(httpx.AsyncBaseTransport):
    """Replays a fixed sequence of outcomes (a response, or an exception to raise) — lets a retry
    test observe the exact attempt count (spec 07 test plan: "fail-fail-succeed observed via a
    counting transport")."""

    def __init__(self, outcomes: list[Exception | httpx.Response]) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


# --- retry -------------------------------------------------------------------------


async def test_retry_succeeds_on_third_attempt_after_two_5xx() -> None:
    transport = _FlakyTransport(
        [httpx.Response(500), httpx.Response(500), httpx.Response(200, json={"ok": True})]
    )
    client = Client(transport=transport)
    response = await client.retry(3, 0).get("https://x.test/flaky")
    assert response.status() == 200
    assert response.json() == {"ok": True}
    assert transport.calls == 3


async def test_retry_exhausted_raises_request_failed() -> None:
    transport = _FlakyTransport([httpx.Response(500), httpx.Response(500)])
    client = Client(transport=transport)
    with pytest.raises(RequestFailed) as exc_info:
        await client.retry(2, 0).get("https://x.test/flaky")
    assert exc_info.value.response.status() == 500
    assert transport.calls == 2


async def test_retry_retries_connect_errors_by_default() -> None:
    transport = _FlakyTransport([httpx.ConnectError("boom"), httpx.Response(200)])
    client = Client(transport=transport)
    response = await client.retry(2, 0).get("https://x.test/flaky")
    assert response.status() == 200
    assert transport.calls == 2


async def test_retry_reraises_the_last_exception_when_exhausted() -> None:
    transport = _FlakyTransport([httpx.ConnectError("boom"), httpx.ConnectError("boom again")])
    client = Client(transport=transport)
    with pytest.raises(httpx.ConnectError, match="boom again"):
        await client.retry(2, 0).get("https://x.test/flaky")
    assert transport.calls == 2


async def test_a_non_retryable_status_is_not_retried() -> None:
    # 404 is a client error, not the default retry-worthy 5xx/connect-error — no retry, no raise.
    transport = _FlakyTransport([httpx.Response(404)])
    client = Client(transport=transport)
    response = await client.retry(3, 0).get("https://x.test/missing")
    assert response.status() == 404
    assert transport.calls == 1


async def test_retry_when_overrides_the_default_policy() -> None:
    # `when` only retries on 429 — a 500 is left alone (no retry, no raise) under this policy.
    transport = _FlakyTransport([httpx.Response(500)])
    client = Client(transport=transport)
    response = await client.retry(
        3, 0, when=lambda r: isinstance(r, ClientResponse) and r.status() == 429
    ).get("https://x.test/flaky")
    assert response.status() == 500
    assert transport.calls == 1


async def test_retry_sleeps_between_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("asyncio.sleep", _fake_sleep)
    transport = _FlakyTransport([httpx.Response(500), httpx.Response(200)])
    client = Client(transport=transport)
    await client.retry(2, 50).get("https://x.test/flaky")
    assert sleeps == [0.05]


# --- timeout / connect_timeout --------------------------------------------------------


async def test_timeout_and_connect_timeout_are_chainable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    client = Client(transport=httpx.MockTransport(handler))
    response = await client.timeout(5).connect_timeout(1).get("https://x.test/")
    assert response.status() == 200


# --- as_form / as_multipart / attach ----------------------------------------------------


async def test_as_form_sends_url_encoded_body() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["content_type"] = request.headers["content-type"]
        seen["body"] = request.content
        return httpx.Response(200)

    client = Client(transport=httpx.MockTransport(handler))
    response = await client.as_form().post("https://x.test/form", data={"name": "Ada"})
    assert response.status() == 200
    assert seen["content_type"].startswith("application/x-www-form-urlencoded")
    assert seen["body"] == b"name=Ada"


async def test_as_multipart_with_attach_sends_a_file_part() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["content_type"] = request.headers["content-type"]
        seen["body"] = request.content
        return httpx.Response(200)

    client = Client(transport=httpx.MockTransport(handler))
    response = await (
        client.as_multipart()
        .attach(
            "avatar", b"\x89PNG-bytes", filename="avatar.png", headers={"Content-Type": "image/png"}
        )
        .post("https://x.test/upload")
    )
    assert response.status() == 200
    assert seen["content_type"].startswith("multipart/form-data")
    assert b'name="avatar"' in seen["body"]
    assert b'filename="avatar.png"' in seen["body"]
    assert b"\x89PNG-bytes" in seen["body"]


# --- accept / accept_json ------------------------------------------------------------


async def test_accept_and_accept_json_set_the_header() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["accept"] = request.headers["accept"]
        return httpx.Response(200)

    client = Client(transport=httpx.MockTransport(handler))
    await client.accept("text/csv").get("https://x.test/")
    assert seen["accept"] == "text/csv"
    await client.accept_json().get("https://x.test/")
    assert seen["accept"] == "application/json"


# --- with_body ------------------------------------------------------------------------


async def test_with_body_sends_raw_content_and_content_type() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["content_type"] = request.headers["content-type"]
        seen["body"] = request.content
        return httpx.Response(200)

    client = Client(transport=httpx.MockTransport(handler))
    await client.with_body("<xml/>", "application/xml").post("https://x.test/raw")
    assert seen["content_type"] == "application/xml"
    assert seen["body"] == b"<xml/>"


# --- with_basic_auth --------------------------------------------------------------------


async def test_with_basic_auth_sets_the_authorization_header() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers["authorization"]
        return httpx.Response(200)

    client = Client(transport=httpx.MockTransport(handler))
    await client.with_basic_auth("ada", "s3cret").get("https://x.test/")
    expected = "Basic " + base64.b64encode(b"ada:s3cret").decode()
    assert seen["authorization"] == expected


# --- with_digest_auth (challenge/response via ASGI transport) -----------------------------


async def _digest_asgi_app(scope: Any, receive: Any, send: Any) -> None:
    assert scope["type"] == "http"
    headers = dict(scope["headers"])
    authorization = headers.get(b"authorization", b"").decode()
    if authorization.startswith("Digest "):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b'{"authenticated": true}'})
        return
    challenge = 'Digest realm="test", qop="auth", nonce="abc123", opaque="xyz"'
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [(b"www-authenticate", challenge.encode())],
        }
    )
    await send({"type": "http.response.body", "body": b""})


async def test_with_digest_auth_completes_the_challenge_response_flow() -> None:
    transport = httpx.ASGITransport(app=_digest_asgi_app)
    client = Client(transport=transport)
    response = await client.with_digest_auth("ada", "s3cret").get("http://digest.test/secure")
    assert response.status() == 200
    assert response.json() == {"authenticated": True}
