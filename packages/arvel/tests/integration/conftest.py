"""Integration-test fixtures — bind a real ReverbServer for end-to-end checks (WI-014)."""

from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncIterator
from contextlib import closing, suppress
from dataclasses import dataclass

import pytest
from arvel.broadcasting.config import ReverbConfig
from arvel.reverb.server import ReverbServer


@dataclass(frozen=True)
class RunningReverbServer:
    """Handle returned by :func:`running_reverb_server` — the server is already serving."""

    host: str
    port: int
    app_id: str
    app_key: str
    server: ReverbServer

    @property
    def ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}"


def _pick_free_port() -> int:
    """Bind ephemeral, immediately release; ports collide rarely enough for tests."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
async def running_reverb_server() -> AsyncIterator[RunningReverbServer]:
    """Boot a real `ReverbServer` on an ephemeral port; tear down on test exit."""
    port = _pick_free_port()
    config = ReverbConfig(
        app_id="test-app",
        key="test-key",
        secret="test-secret",
        host="127.0.0.1",
        port=port,
        allowed_origins=["*"],  # tests run from localhost — opt into any-origin
    )
    server = ReverbServer(config=config)
    serve_task = asyncio.create_task(server.serve(config.host, config.port))
    # Yield to the loop so `websockets.serve` actually binds before the test connects.
    await asyncio.sleep(0.05)
    try:
        yield RunningReverbServer(
            host=config.host,
            port=port,
            app_id=config.app_id,
            app_key=config.key,
            server=server,
        )
    finally:
        serve_task.cancel()
        with suppress(asyncio.CancelledError):
            await serve_task
