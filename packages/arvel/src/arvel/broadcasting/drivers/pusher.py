"""PusherBroadcaster — HTTP POST to api-<cluster>.pusher.com (FR-013-005)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Mapping, Sequence
from typing import Any, Protocol, Self, cast
from urllib.parse import urlencode

from arvel.broadcasting.exceptions import BroadcastDriverError


class _HttpResponse(Protocol):
    @property
    def status_code(self) -> int: ...

    @property
    def text(self) -> str: ...


class _HttpClient(Protocol):
    """Subset of httpx.AsyncClient used by PusherBroadcaster."""

    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, *args: object) -> None: ...

    async def post(
        self,
        url: str,
        params: dict[str, str],
        json: dict[str, Any],
    ) -> _HttpResponse: ...


def _default_client_factory() -> _HttpClient:
    import httpx

    # httpx.AsyncClient.post accepts a superset of our Protocol signature; the
    # narrow cast keeps the boundary type-safe for callers.
    return cast("_HttpClient", httpx.AsyncClient(timeout=10.0))


class PusherBroadcaster:
    """Pusher Channels HTTP API driver (FR-013-005, ADR-057-style)."""

    def __init__(
        self,
        *,
        app_id: str,
        key: str,
        secret: str,
        cluster: str = "mt1",
        host: str | None = None,
        _client_factory: Any = None,
    ) -> None:
        self._app_id: str = app_id
        self._key: str = key
        self._secret: str = secret
        self._host: str = host or f"api-{cluster}.pusher.com"
        self._client_factory: Any = _client_factory or _default_client_factory

    async def broadcast(
        self,
        channels: Sequence[str],
        event: str,
        payload: Mapping[str, object],
        *,
        except_socket_id: str | None = None,
    ) -> None:
        try:
            data = json.dumps(dict(payload))
        except (TypeError, ValueError) as exc:
            raise BroadcastDriverError(
                f"PusherBroadcaster cannot serialize payload for {event!r}: {exc}",
            ) from exc

        body: dict[str, Any] = {
            "name": event,
            "data": data,
            "channels": list(channels),
        }
        if except_socket_id is not None:
            body["socket_id"] = except_socket_id

        path = f"/apps/{self._app_id}/events"
        # MD5 here is a body integrity check required by the Pusher v1 REST
        # signing protocol — not used as a cryptographic primitive.
        # https://pusher.com/docs/channels/library_auth_reference/rest-api/
        body_md5 = hashlib.md5(
            json.dumps(body).encode(),
            usedforsecurity=False,
        ).hexdigest()
        params = {
            "auth_key": self._key,
            "auth_timestamp": str(int(time.time())),
            "auth_version": "1.0",
            "body_md5": body_md5,
        }
        auth_string = f"POST\n{path}\n" + urlencode(sorted(params.items()))
        params["auth_signature"] = hmac.new(
            self._secret.encode(),
            auth_string.encode(),
            hashlib.sha256,
        ).hexdigest()

        url = f"https://{self._host}{path}"
        async with self._client_factory() as client:
            response = await client.post(url, params=params, json=body)
        if response.status_code >= 400:  # noqa: PLR2004
            raise BroadcastDriverError(
                f"Pusher API returned {response.status_code}: {response.text}",
            )


__all__ = ["PusherBroadcaster"]
