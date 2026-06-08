"""TrustProxiesMiddleware — honor X-Forwarded-* only behind a trusted peer."""

from __future__ import annotations

import asyncio

import pytest
from starlette.types import Message, Receive, Scope, Send


def _run(scope: Scope) -> Scope:
    """Drive the middleware once and return the scope the inner app saw."""
    from arvel.http.middleware import TrustProxiesMiddleware

    seen: dict[str, Scope] = {}

    async def inner(inner_scope: Scope, _receive: Receive, _send: Send) -> None:
        seen["scope"] = inner_scope

    trusted = scope.pop("_trusted", ["10.0.0.0/8"])  # type: ignore[assignment]
    app = TrustProxiesMiddleware(inner, trusted_proxies=list(trusted))

    async def noop_receive() -> Message:
        return {"type": "http.request"}

    async def noop_send(_message: Message) -> None:
        pass

    asyncio.run(app(scope, noop_receive, noop_send))
    return seen["scope"]


def _http_scope(
    *,
    client: tuple[str, int],
    headers: list[tuple[bytes, bytes]] | None = None,
    trusted: list[str] | None = None,
) -> Scope:
    scope: Scope = {
        "type": "http",
        "scheme": "http",
        "path": "/",
        "client": client,
        "headers": headers or [],
    }
    if trusted is not None:
        scope["_trusted"] = trusted
    return scope


def _host_header(scope: Scope) -> str | None:
    for name, value in scope["headers"]:
        if name == b"host":
            return value.decode("latin-1")
    return None


def test_untrusted_peer_ignores_forwarded_headers() -> None:
    scope = _http_scope(
        client=("203.0.113.9", 5000),
        headers=[
            (b"x-forwarded-for", b"1.2.3.4"),
            (b"x-forwarded-proto", b"https"),
            (b"x-forwarded-host", b"public.example.com"),
        ],
        trusted=["10.0.0.0/8"],
    )
    seen = _run(scope)
    # Peer is not in the trusted range → nothing is rewritten.
    assert seen["client"] == ("203.0.113.9", 5000)
    assert seen["scheme"] == "http"
    assert _host_header(seen) is None


def test_trusted_peer_resolves_client_ip_from_xff() -> None:
    scope = _http_scope(
        client=("10.0.0.5", 5000),
        headers=[(b"x-forwarded-for", b"1.2.3.4, 10.0.0.5")],
        trusted=["10.0.0.0/8"],
    )
    seen = _run(scope)
    # Right-to-left, skip the trusted hop (10.0.0.5) → real client 1.2.3.4.
    assert seen["client"] == ("1.2.3.4", 5000)


def test_trusted_peer_sets_scheme_from_proto() -> None:
    scope = _http_scope(
        client=("10.0.0.5", 5000),
        headers=[(b"x-forwarded-proto", b"https")],
        trusted=["10.0.0.0/8"],
    )
    seen = _run(scope)
    assert seen["scheme"] == "https"


def test_trusted_peer_sets_host_from_forwarded_host() -> None:
    scope = _http_scope(
        client=("10.0.0.5", 5000),
        headers=[(b"host", b"internal:8000"), (b"x-forwarded-host", b"public.example.com")],
        trusted=["10.0.0.0/8"],
    )
    seen = _run(scope)
    assert _host_header(seen) == "public.example.com"


def test_trust_all_picks_leftmost_xff_entry() -> None:
    scope = _http_scope(
        client=("10.0.0.5", 5000),
        headers=[(b"x-forwarded-for", b"1.2.3.4, 5.6.7.8, 10.0.0.5")],
        trusted=["*"],
    )
    seen = _run(scope)
    # Every hop trusted → the original client is the first (leftmost) entry.
    assert seen["client"] == ("1.2.3.4", 5000)


def test_trusted_peer_without_xff_keeps_peer() -> None:
    scope = _http_scope(
        client=("10.0.0.5", 5000),
        headers=[(b"x-forwarded-proto", b"https")],
        trusted=["10.0.0.0/8"],
    )
    seen = _run(scope)
    assert seen["client"] == ("10.0.0.5", 5000)


def test_invalid_proto_is_ignored() -> None:
    scope = _http_scope(
        client=("10.0.0.5", 5000),
        headers=[(b"x-forwarded-proto", b"gopher")],
        trusted=["10.0.0.0/8"],
    )
    seen = _run(scope)
    assert seen["scheme"] == "http"


def test_lifespan_scope_passthrough() -> None:
    from arvel.http.middleware import TrustProxiesMiddleware

    called: list[str] = []

    async def inner(scope: Scope, _receive: Receive, _send: Send) -> None:
        called.append(scope["type"])

    app = TrustProxiesMiddleware(inner, trusted_proxies=["*"])

    async def run() -> None:
        scope: Scope = {"type": "lifespan"}

        async def recv() -> Message:
            return {"type": "lifespan.startup"}

        async def snd(_m: Message) -> None:
            pass

        await app(scope, recv, snd)

    asyncio.run(run())
    assert called == ["lifespan"]


def test_websocket_maps_https_to_wss() -> None:
    from arvel.http.middleware import TrustProxiesMiddleware

    seen: dict[str, Scope] = {}

    async def inner(scope: Scope, _receive: Receive, _send: Send) -> None:
        seen["scope"] = scope

    app = TrustProxiesMiddleware(inner, trusted_proxies=["10.0.0.0/8"])

    async def run() -> None:
        scope: Scope = {
            "type": "websocket",
            "scheme": "ws",
            "path": "/ws",
            "client": ("10.0.0.5", 5000),
            "headers": [(b"x-forwarded-proto", b"https")],
        }

        async def recv() -> Message:
            return {"type": "websocket.connect"}

        async def snd(_m: Message) -> None:
            pass

        await app(scope, recv, snd)

    asyncio.run(run())
    assert seen["scope"]["scheme"] == "wss"


def test_importable_from_package_and_module() -> None:
    from arvel.http.middleware import TrustProxiesMiddleware
    from arvel.http.middleware.trust_proxies import (
        TrustProxiesMiddleware as Alias,
    )

    assert TrustProxiesMiddleware is Alias


def test_config_parses_trusted_proxies_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    from arvel.http.config import HttpConfig

    monkeypatch.setenv("TRUSTED_PROXIES", "10.0.0.0/8, 192.168.0.0/16")
    config = HttpConfig.from_environment()
    assert config.trusted_proxies == ["10.0.0.0/8", "192.168.0.0/16"]


def test_config_defaults_to_empty() -> None:
    from arvel.http.config import HttpConfig

    config = HttpConfig.from_environment()
    assert config.trusted_proxies == []
