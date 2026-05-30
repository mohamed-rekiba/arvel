"""FR-013-018, FR-013-022, NFR-013-005 — Pusher protocol v7 frame shapes."""

from __future__ import annotations

import json


def test_pusher_connection_established_frame_shape() -> None:
    """FR-013-018 AC1: connection_established frame matches Pusher v7 spec."""
    from arvel.reverb.protocol import build_connection_established

    frame = build_connection_established(socket_id="123.456", activity_timeout=120)
    parsed = json.loads(frame)
    assert parsed["event"] == "pusher:connection_established"
    data = json.loads(parsed["data"])
    assert data["socket_id"] == "123.456"
    assert data["activity_timeout"] == 120


def test_pusher_subscription_succeeded_frame_shape() -> None:
    """FR-013-018 AC2: pusher_internal:subscription_succeeded carries channel + optional data."""
    from arvel.reverb.protocol import build_subscription_succeeded

    frame = build_subscription_succeeded(channel="orders", presence_data=None)
    parsed = json.loads(frame)
    assert parsed["event"] == "pusher_internal:subscription_succeeded"
    assert parsed["channel"] == "orders"


def test_pusher_error_frame_shape() -> None:
    """FR-013-018 AC3: pusher:error frames carry code + message."""
    from arvel.reverb.protocol import build_error

    frame = build_error(code=4001, message="Invalid signature")
    parsed = json.loads(frame)
    assert parsed["event"] == "pusher:error"
    data = json.loads(parsed["data"])
    assert data["code"] == 4001
    assert data["message"] == "Invalid signature"


def test_pong_frame_shape() -> None:
    """FR-013-022 AC2: pong frame echoes the pusher:pong event."""
    from arvel.reverb.protocol import build_pong

    parsed = json.loads(build_pong())
    assert parsed["event"] == "pusher:pong"


def test_event_frame_includes_channel() -> None:
    """NFR-013-005: server-to-client event frame mirrors Pusher v7."""
    from arvel.reverb.protocol import build_event_frame

    frame = build_event_frame(channel="orders", event="OrderShipped", data={"order_id": 42})
    parsed = json.loads(frame)
    assert parsed["channel"] == "orders"
    assert parsed["event"] == "OrderShipped"
    assert json.loads(parsed["data"]) == {"order_id": 42}


def test_member_added_frame_shape() -> None:
    """FR-013-021 AC3: presence member_added frame carries user info."""
    from arvel.reverb.protocol import build_member_added

    frame = build_member_added(
        channel="presence-room.7",
        user_id="u-42",
        user_info={"name": "Alice"},
    )
    parsed = json.loads(frame)
    assert parsed["event"] == "pusher_internal:member_added"
    data = json.loads(parsed["data"])
    assert data["user_id"] == "u-42"
    assert data["user_info"] == {"name": "Alice"}
