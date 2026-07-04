"""Http.fake — wildcard stubs, assertions, stray-request prevention, restore (spec 07 §4)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from arvel.client import Client, RecordedRequest, StrayRequest


async def test_fake_returns_the_stub_without_network() -> None:
    client = Client()
    with client.fake({"https://example.com/*": client.response(body={"id": 1}, status=201)}):
        response = await client.get("https://example.com/users/1")
    assert response.status() == 201
    assert response.json() == {"id": 1}


async def test_fake_wildcard_matches_full_url() -> None:
    client = Client()
    with client.fake({"*.example.com/*": client.response(body="ok")}):
        response = await client.get("https://api.example.com/v1/ping")
    assert response.body() == "ok"


async def test_fake_first_matching_pattern_wins() -> None:
    client = Client()
    with client.fake(
        {
            "https://example.com/users/*": client.response(body="specific"),
            "https://example.com/*": client.response(body="generic"),
        }
    ):
        response = await client.get("https://example.com/users/1")
    assert response.body() == "specific"


async def test_fake_callable_stub_receives_the_recorded_request() -> None:
    client = Client()

    def stub(request: RecordedRequest) -> Any:
        return client.response(body={"echo": request.method})

    with client.fake({"https://example.com/*": stub}):
        response = await client.post("https://example.com/echo")
    assert response.json() == {"echo": "POST"}


async def test_fake_with_no_mapping_stubs_everything_with_a_default_200() -> None:
    client = Client()
    with client.fake():
        response = await client.get("https://anything.test/whatever")
    assert response.status() == 200


async def test_restore_reverts_to_the_real_transport() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"real": True})

    client = Client(transport=httpx.MockTransport(handler))
    client.fake({"https://example.com/*": client.response(body={"fake": True})})
    faked = await client.get("https://example.com/x")
    assert faked.json() == {"fake": True}

    client.restore()
    real = await client.get("https://example.com/x")
    assert real.json() == {"real": True}


async def test_fake_used_as_a_plain_call_without_with_block() -> None:
    client = Client()
    client.fake({"https://example.com/*": client.response(body="stubbed")})
    try:
        response = await client.get("https://example.com/x")
        assert response.body() == "stubbed"
    finally:
        client.restore()


# --- prevent_stray_requests --------------------------------------------------------------


async def test_prevent_stray_requests_raises_for_an_unmatched_url() -> None:
    client = Client()
    with client.fake({"https://example.com/*": client.response(body="ok")}):
        client.prevent_stray_requests()
        with pytest.raises(StrayRequest):
            await client.get("https://other.test/whatever")


async def test_without_prevent_stray_requests_an_unmatched_url_passes_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No pattern matches → the real network — proven deterministically by monkeypatching the
    passthrough's `httpx.AsyncClient` onto a mock transport."""
    import arvel.client as client_module

    def passthrough_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"passed_through": True})

    real_async_client = httpx.AsyncClient

    class _PatchedAsyncClient(real_async_client):  # type: ignore[misc]
        # Only the *passthrough* `httpx.AsyncClient()` call (inside `_FakeState.handle`) omits
        # `transport=`; the outer per-request client always passes the fake's own transport
        # explicitly, so `setdefault` leaves that one alone.
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("transport", httpx.MockTransport(passthrough_handler))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(client_module.httpx, "AsyncClient", _PatchedAsyncClient)

    client = Client()
    with client.fake({"https://example.com/*": client.response(body="ok")}):
        response = await client.get("https://other.test/whatever")
    assert response.json() == {"passed_through": True}


async def test_prevent_stray_requests_requires_an_active_fake() -> None:
    client = Client()
    with pytest.raises(RuntimeError):
        client.prevent_stray_requests()


# --- assertions ----------------------------------------------------------------------------


async def test_assert_sent_and_assert_not_sent() -> None:
    client = Client()
    with client.fake({"https://example.com/*": client.response(body="ok")}):
        await client.post("https://example.com/users", json={"name": "Ada"})

        client.assert_sent(lambda r: r.method == "POST" and r.url == "https://example.com/users")
        client.assert_not_sent(lambda r: r.method == "GET")

        with pytest.raises(AssertionError):
            client.assert_sent(lambda r: r.method == "DELETE")
        with pytest.raises(AssertionError):
            client.assert_not_sent(lambda r: r.method == "POST")


async def test_assert_sent_count() -> None:
    client = Client()
    with client.fake({"https://example.com/*": client.response(body="ok")}):
        await client.get("https://example.com/a")
        await client.get("https://example.com/b")
        client.assert_sent_count(2)
        with pytest.raises(AssertionError):
            client.assert_sent_count(1)


async def test_recorded_returns_requests_with_bodies_readable_via_dotted_json() -> None:
    client = Client()
    with client.fake({"https://example.com/*": client.response(body="ok")}):
        await client.post("https://example.com/users", json={"user": {"name": "Ada"}})
        recorded = client.recorded()
        assert len(recorded) == 1
        assert recorded[0].json("user.name") == "Ada"


async def test_recorded_is_empty_when_no_fake_is_active() -> None:
    client = Client()
    assert client.recorded() == []
