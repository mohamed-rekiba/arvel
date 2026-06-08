"""Test helpers shared across arvel-oauth test modules."""

from __future__ import annotations

from collections.abc import Callable

import httpx2 as httpx


def mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    """An httpx.AsyncClient backed by a routing handler — no real network."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))
