"""Driver behaviour tests (log, null, redis, pusher)."""

from __future__ import annotations

import json
from typing import Any, Self
from unittest.mock import AsyncMock, patch

import pytest

# ─── — LogBroadcaster ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_broadcaster_emits_structured_event(caplog: pytest.LogCaptureFixture) -> None:
    """emits exactly one structured log event named broadcast_emitted."""
    from arvel.broadcasting.drivers.log import LogBroadcaster

    log = LogBroadcaster()
    with caplog.at_level("INFO"):
        await log.broadcast(["orders"], "OrderShipped", {"order_id": 42})
    assert any("broadcast_emitted" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_log_broadcaster_omits_payload_values() -> None:
    """/ : payload values are NOT included in the log; only keys."""
    import logging as _logging

    from arvel.broadcasting.drivers.log import LogBroadcaster

    log = LogBroadcaster()
    records: list[_logging.LogRecord] = []

    class _Sink(_logging.Handler):
        def emit(self, record: _logging.LogRecord) -> None:
            records.append(record)

    root = _logging.getLogger()
    sink = _Sink()
    sink.setLevel(_logging.INFO)
    root.addHandler(sink)
    prior_level = root.level
    root.setLevel(_logging.INFO)
    try:
        await log.broadcast(["orders"], "OrderShipped", {"order_id": 42, "user_id": 99})
    finally:
        root.removeHandler(sink)
        root.setLevel(prior_level)

    rendered = " ".join(r.getMessage() for r in records)
    assert "order_id" in rendered  # key present
    assert "42" not in rendered  # value absent
    assert "99" not in rendered  # value absent


@pytest.mark.asyncio
async def test_log_broadcaster_no_args_constructor() -> None:
    """constructor takes no arguments."""
    from arvel.broadcasting.drivers.log import LogBroadcaster

    LogBroadcaster()  # MUST NOT raise


# ─── — NullBroadcaster ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_null_broadcaster_is_noop() -> None:
    """broadcast is a no-op that returns None."""
    from arvel.broadcasting.drivers.null import NullBroadcaster

    # broadcast() is typed -> None; calling it must not raise.
    await NullBroadcaster().broadcast(["any"], "Any", {"k": "v"})


@pytest.mark.asyncio
async def test_null_broadcaster_accepts_empty_channels() -> None:
    """never raises under any input including channels=[]."""
    from arvel.broadcasting.drivers.null import NullBroadcaster

    await NullBroadcaster().broadcast([], "Any", {})


# ─── — RedisBroadcaster ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_redis_broadcaster_publishes_per_channel() -> None:
    """one Redis PUBLISH per channel in the list."""
    from arvel.broadcasting.drivers.redis import RedisBroadcaster

    fake_client = AsyncMock()
    fake_client.publish = AsyncMock()
    broadcaster = RedisBroadcaster(redis=fake_client)
    await broadcaster.broadcast(
        ["private-user.5", "orders"],
        "OrderShipped",
        {"order_id": 42},
    )
    assert fake_client.publish.await_count == 2


@pytest.mark.asyncio
async def test_redis_broadcaster_uses_prefixed_channel_key() -> None:
    """channel key is `arvel.broadcasting.{channel}`."""
    from arvel.broadcasting.drivers.redis import RedisBroadcaster

    fake_client = AsyncMock()
    fake_client.publish = AsyncMock()
    broadcaster = RedisBroadcaster(redis=fake_client)
    await broadcaster.broadcast(["private-user.5"], "X", {})
    args, _ = fake_client.publish.call_args
    assert args[0] == "arvel.broadcasting.private-user.5"


@pytest.mark.asyncio
async def test_redis_broadcaster_payload_is_valid_json() -> None:
    """payload encoded with json.dumps."""
    from arvel.broadcasting.drivers.redis import RedisBroadcaster

    fake_client = AsyncMock()
    fake_client.publish = AsyncMock()
    broadcaster = RedisBroadcaster(redis=fake_client)
    await broadcaster.broadcast(["orders"], "X", {"k": "v"})
    args, _ = fake_client.publish.call_args
    body = json.loads(args[1])
    assert body["event"] == "X"
    assert body["data"] == {"k": "v"}


@pytest.mark.asyncio
async def test_redis_broadcaster_rejects_non_serializable_payload() -> None:
    """raise BroadcastDriverError on non-JSON payload."""
    from arvel.broadcasting.drivers.redis import RedisBroadcaster
    from arvel.broadcasting.exceptions import BroadcastDriverError

    fake_client = AsyncMock()
    broadcaster = RedisBroadcaster(redis=fake_client)
    with pytest.raises(BroadcastDriverError):
        await broadcaster.broadcast(["x"], "X", {"obj": object()})


def test_redis_broadcaster_raises_when_redis_extra_missing() -> None:
    """missing dep raises BroadcastDriverError on resolve."""
    import sys

    from arvel.broadcasting.config import BroadcastConfig, BroadcastDriver
    from arvel.broadcasting.exceptions import BroadcastDriverError
    from arvel.broadcasting.manager import BroadcastManager

    with patch.dict(sys.modules, {"redis": None, "redis.asyncio": None}):
        config = BroadcastConfig(default=BroadcastDriver.REDIS_PUBSUB)
        manager = BroadcastManager(config)
        with pytest.raises(BroadcastDriverError, match=r"arvel\[redis\]"):
            manager.driver()


# ─── — PusherBroadcaster ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_pusher_broadcaster_posts_to_events_endpoint() -> None:
    """+: posts to /apps/{app_id}/events with signed params."""
    from arvel.broadcasting.drivers.pusher import PusherBroadcaster

    sent_requests: list[Any] = []

    class _FakeClient:
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

        async def post(self, url: str, params: dict[str, str], json: dict[str, Any]) -> Any:
            sent_requests.append((url, params, json))

            class _Resp:
                status_code = 200

            return _Resp()

    broadcaster = PusherBroadcaster(
        app_id="123",
        key="k",
        secret="s",
        cluster="mt1",
        _client_factory=_FakeClient,
    )
    await broadcaster.broadcast(["orders"], "OrderShipped", {"order_id": 42})

    assert len(sent_requests) == 1
    url, params, _body = sent_requests[0]
    assert url.endswith("/apps/123/events")
    assert "auth_key" in params
    assert "auth_signature" in params
    assert "auth_timestamp" in params
    assert params["auth_version"] == "1.0"


@pytest.mark.asyncio
async def test_pusher_broadcaster_raises_on_failed_request() -> None:
    """failed HTTP request raises BroadcastDriverError."""
    from arvel.broadcasting.drivers.pusher import PusherBroadcaster
    from arvel.broadcasting.exceptions import BroadcastDriverError

    class _FakeClient:
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

        async def post(self, *a: Any, **kw: Any) -> Any:
            class _Resp:
                status_code = 500
                text = "boom"

            return _Resp()

    broadcaster = PusherBroadcaster(
        app_id="x",
        key="k",
        secret="s",
        cluster="mt1",
        _client_factory=_FakeClient,
    )
    with pytest.raises(BroadcastDriverError, match="500"):
        await broadcaster.broadcast(["x"], "X", {})
