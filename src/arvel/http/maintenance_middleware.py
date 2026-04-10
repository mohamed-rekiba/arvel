"""ASGI middleware for maintenance mode.

Reads the maintenance signal file on each HTTP request. If the file exists,
returns 503 Service Unavailable — unless the request is exempt (health
endpoint, bypass secret, or IP allowlist).
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs

if TYPE_CHECKING:
    from pathlib import Path

ASGIApp = Any
Scope = dict[str, Any]
Receive = Any
Send = Any

_EXEMPT_PATHS = frozenset({"/health", "/health/"})


class MaintenanceMiddleware:
    """Pure ASGI middleware that returns 503 when maintenance mode is active."""

    def __init__(self, app: ASGIApp, *, maintenance_path: Path) -> None:
        self._app = app
        self._maintenance_path = maintenance_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        if not self._maintenance_path.exists():
            await self._app(scope, receive, send)
            return

        try:
            data = json.loads(self._maintenance_path.read_text())
        except json.JSONDecodeError, OSError:
            await self._app(scope, receive, send)
            return

        request_path: str = scope.get("path", "")
        if request_path in _EXEMPT_PATHS:
            await self._app(scope, receive, send)
            return

        if self._check_secret_bypass(scope, data):
            await self._app(scope, receive, send)
            return

        if self._check_ip_bypass(scope, data):
            await self._app(scope, receive, send)
            return

        await self._send_503(send, data)

    @staticmethod
    def _check_secret_bypass(scope: Scope, data: dict[str, Any]) -> bool:
        stored_hash = data.get("secret_hash")
        if not stored_hash:
            return False

        qs = scope.get("query_string", b"")
        if isinstance(qs, str):
            qs = qs.encode()
        params = parse_qs(qs.decode("latin-1"))
        provided = params.get("secret", [None])[0]
        if not provided:
            return False

        computed = "sha256:" + hashlib.sha256(provided.encode()).hexdigest()
        return computed == stored_hash

    @staticmethod
    def _check_ip_bypass(scope: Scope, data: dict[str, Any]) -> bool:
        allowed_ips: list[str] = data.get("allowed_ips", [])
        if not allowed_ips:
            return False

        client = scope.get("client")
        if not client:
            return False

        client_ip = client[0]
        try:
            addr = ipaddress.ip_address(client_ip)
        except ValueError:
            return False

        for cidr in allowed_ips:
            try:
                if addr in ipaddress.ip_network(cidr, strict=False):
                    return True
            except ValueError:
                continue

        return False

    @staticmethod
    async def _send_503(send: Send, data: dict[str, Any]) -> None:
        headers: list[tuple[bytes, bytes]] = [
            (b"content-type", b"application/json"),
        ]

        retry_after = data.get("retry_after")
        if retry_after is not None:
            headers.append((b"retry-after", str(retry_after).encode()))

        body = json.dumps({"message": "Service Unavailable — maintenance mode"}).encode()

        await send(
            {
                "type": "http.response.start",
                "status": 503,
                "headers": headers,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body,
            }
        )
