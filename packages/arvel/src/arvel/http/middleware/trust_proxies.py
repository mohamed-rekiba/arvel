"""TrustProxiesMiddleware — honor ``X-Forwarded-*`` behind trusted proxies.

Behind a load balancer the ASGI ``scope["client"]`` is the proxy, the scheme is
the internal (often plaintext) scheme, and the host is internal. The real values
arrive in ``X-Forwarded-For`` / ``-Proto`` / ``-Host``. Those headers are
client-controlled, so we only honor them when the TCP peer is a configured
trusted proxy — otherwise anyone could spoof their IP, scheme, or host.

Mounted as the outermost layer so every downstream middleware and handler
(rate limiting, signed-URL checks, redirects, logging) sees a corrected scope.
"""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from arvel.observability.forwarded import ip_in_cidrs, resolve_client_ip

# "*" means trust every peer; expands to the IPv4 + IPv6 "any" networks.
_TRUST_ALL_CIDRS = ("0.0.0.0/0", "::/0")
_VALID_SCHEMES = frozenset({"http", "https"})


def _expand_proxies(trusted_proxies: list[str]) -> tuple[list[str], bool]:
    """Return (peer-trust CIDRs, trust_all). ``*`` -> any-network CIDRs."""
    if any(p.strip() == "*" for p in trusted_proxies):
        return list(_TRUST_ALL_CIDRS), True
    return [p.strip() for p in trusted_proxies if p.strip()], False


def _client_ip(*, peer_ip: str, xff: str | None, cidrs: list[str], trust_all: bool) -> str:
    if not xff:
        return peer_ip
    if trust_all:
        # Every hop is trusted, so the original client is the leftmost entry.
        hops = [h.strip() for h in xff.split(",") if h.strip()]
        return hops[0] if hops else peer_ip
    return resolve_client_ip(peer_ip=peer_ip, forwarded_for=xff, trusted_proxies=cidrs)


def _scheme_for(scope_type: str, proto: str) -> str | None:
    scheme = proto.split(",", 1)[0].strip().lower()
    if scheme not in _VALID_SCHEMES:
        return None
    if scope_type == "websocket":
        return "wss" if scheme == "https" else "ws"
    return scheme


def _with_host_header(
    raw_headers: list[tuple[bytes, bytes]], host: str
) -> list[tuple[bytes, bytes]]:
    rewritten = [(name, value) for name, value in raw_headers if name != b"host"]
    rewritten.append((b"host", host.encode("latin-1")))
    return rewritten


class TrustProxiesMiddleware:
    """Rewrite the ASGI scope from ``X-Forwarded-*`` when the peer is trusted."""

    def __init__(self, app: ASGIApp, *, trusted_proxies: list[str]) -> None:
        self._app = app
        self._cidrs, self._trust_all = _expand_proxies(trusted_proxies)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return

        client = scope.get("client")
        peer_ip = client[0] if client else None
        if peer_ip is None or not ip_in_cidrs(peer_ip, self._cidrs):
            await self._app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        resolved = _client_ip(
            peer_ip=peer_ip,
            xff=headers.get("x-forwarded-for"),
            cidrs=self._cidrs,
            trust_all=self._trust_all,
        )
        port = client[1] if client else 0
        scope["client"] = (resolved, port)

        proto = headers.get("x-forwarded-proto")
        if proto:
            scheme = _scheme_for(scope["type"], proto)
            if scheme is not None:
                scope["scheme"] = scheme

        forwarded_host = headers.get("x-forwarded-host")
        if forwarded_host:
            host = forwarded_host.split(",", 1)[0].strip()
            scope["headers"] = _with_host_header(list(scope["headers"]), host)

        await self._app(scope, receive, send)


__all__ = ["TrustProxiesMiddleware"]
