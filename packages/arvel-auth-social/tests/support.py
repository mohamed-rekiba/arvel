"""Test helpers shared across arvel-auth-social test modules."""

from __future__ import annotations

from collections.abc import Callable

import httpx


def mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    """An httpx.AsyncClient backed by a routing handler — no real network."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))
