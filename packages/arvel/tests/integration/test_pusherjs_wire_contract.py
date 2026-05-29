"""Pusher v7 wire-contract test (FR-014-006/007/008/009, SEC-014-003).

Boots a real ReverbServer fixture, spawns a Node 20.x subprocess running
pusher-js@8.5.0 against it, and asserts the documented Pusher v7 frame
sequence appears in order on the subprocess's stdout.

Skips with a clear message when `node` is not available on PATH (FR-014-008).
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

if TYPE_CHECKING:
    # Yielded by the `running_reverb_server` fixture in this directory's conftest.py.
    from .conftest import RunningReverbServer

# Path to the Node harness directory (FR-014-009).
_HARNESS_DIR = Path(__file__).parent / "pusher_js_harness"
_HARNESS_SCRIPT = _HARNESS_DIR / "client.mjs"
_HARNESS_PUSHER_PKG = _HARNESS_DIR / "node_modules" / "pusher-js" / "package.json"


def _harness_skip_reason() -> str | None:
    """Return ``None`` when the harness can run; otherwise a clear skip reason.

    Mirrors the storage / emulator skip pattern: an integration test that
    depends on an external runtime skips cleanly when that runtime isn't
    available, with a message that names the exact setup command.
    """
    if shutil.which("node") is None:
        return "requires Node 20.x on PATH"
    if not _HARNESS_SCRIPT.exists():
        return f"harness script missing: {_HARNESS_SCRIPT}"
    if not _HARNESS_PUSHER_PKG.exists():
        return (
            "pusher-js harness deps not installed; run "
            "`npm ci` in packages/arvel/tests/integration/pusher_js_harness/"
        )
    return None


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        _harness_skip_reason() is not None,
        reason=_harness_skip_reason() or "",
    ),
]


async def _read_line(stream: asyncio.StreamReader, *, deadline_seconds: float) -> dict[str, Any]:
    """Read one JSON-encoded event from the harness stdout."""
    raw = await asyncio.wait_for(stream.readline(), timeout=deadline_seconds)
    if not raw:
        msg = "harness closed stdout without writing"
        raise AssertionError(msg)
    decoded = json.loads(raw.decode("utf-8").strip())
    return cast("dict[str, Any]", decoded)


@pytest.mark.asyncio
async def test_pusherjs_connection_established(running_reverb_server: RunningReverbServer) -> None:
    """FR-014-007 — pusher-js receives pusher:connection_established on connect."""
    # SEC-014-003: shell=False, explicit argv list, asyncio.wait_for timeout.
    proc = await asyncio.create_subprocess_exec(
        "node",
        str(_HARNESS_SCRIPT),
        "--url",
        running_reverb_server.ws_url,
        "--key",
        running_reverb_server.app_key,
        "--channel",
        "demo-channel",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        assert proc.stdout is not None
        event = await _read_line(proc.stdout, deadline_seconds=10.0)
        assert event["event"] == "pusher:connection_established"
        data: object = event.get("data")
        if isinstance(data, str):
            data = json.loads(data)
        assert isinstance(data, dict)
        data_dict = cast("dict[str, Any]", data)
        assert "socket_id" in data_dict
    finally:
        proc.terminate()
        await asyncio.wait_for(proc.wait(), timeout=5.0)


@pytest.mark.asyncio
async def test_pusherjs_subscription_succeeded(running_reverb_server: RunningReverbServer) -> None:
    """FR-014-007 — public-channel subscribe triggers pusher_internal:subscription_succeeded."""
    proc = await asyncio.create_subprocess_exec(
        "node",
        str(_HARNESS_SCRIPT),
        "--url",
        running_reverb_server.ws_url,
        "--key",
        running_reverb_server.app_key,
        "--channel",
        "demo-channel",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        assert proc.stdout is not None
        # Drain frames until we see the subscription-succeeded frame.
        for _ in range(10):
            event = await _read_line(proc.stdout, deadline_seconds=10.0)
            if event["event"] == "pusher_internal:subscription_succeeded":
                assert event["channel"] == "demo-channel"
                return
        pytest.fail("did not see pusher_internal:subscription_succeeded within 10 frames")
    finally:
        proc.terminate()
        await asyncio.wait_for(proc.wait(), timeout=5.0)


@pytest.mark.asyncio
async def test_pusherjs_receives_published_event(
    running_reverb_server: RunningReverbServer,
) -> None:
    """FR-014-007 — broadcast reaches subscriber with shape {event, channel, data}."""
    proc = await asyncio.create_subprocess_exec(
        "node",
        str(_HARNESS_SCRIPT),
        "--url",
        running_reverb_server.ws_url,
        "--key",
        running_reverb_server.app_key,
        "--channel",
        "demo-channel",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        assert proc.stdout is not None
        # Wait for subscription_succeeded first.
        for _ in range(10):
            event = await _read_line(proc.stdout, deadline_seconds=10.0)
            if event["event"] == "pusher_internal:subscription_succeeded":
                break
        # Publish through ChannelManager directly (the in-process route).
        await running_reverb_server.server.channels.publish(
            "demo-channel",
            "tick",
            {"counter": 1, "ts": "2026-05-19T00:00:00Z"},
        )
        # Now wait for the custom event.
        for _ in range(10):
            event = await _read_line(proc.stdout, deadline_seconds=5.0)
            if event["event"] == "tick":
                assert event["channel"] == "demo-channel"
                data: object = event.get("data")
                if isinstance(data, str):
                    data = json.loads(data)
                assert isinstance(data, dict)
                data_dict = cast("dict[str, Any]", data)
                assert data_dict.get("counter") == 1
                return
        pytest.fail("did not receive tick event")
    finally:
        proc.terminate()
        await asyncio.wait_for(proc.wait(), timeout=5.0)


@pytest.mark.asyncio
async def test_pusherjs_wire_contract_meets_30s_budget(
    running_reverb_server: RunningReverbServer,
) -> None:
    """NFR-014-001 — wire-contract harness completes in <= 30s wall-clock on CI."""

    async def _run() -> None:
        proc = await asyncio.create_subprocess_exec(
            "node",
            str(_HARNESS_SCRIPT),
            "--url",
            running_reverb_server.ws_url,
            "--key",
            running_reverb_server.app_key,
            "--channel",
            "demo-channel",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            assert proc.stdout is not None
            for _ in range(10):
                event = await _read_line(proc.stdout, deadline_seconds=5.0)
                if event["event"] == "pusher_internal:subscription_succeeded":
                    return
            pytest.fail("subscription_succeeded not observed inside 30s budget")
        finally:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=5.0)

    await asyncio.wait_for(_run(), timeout=30.0)
