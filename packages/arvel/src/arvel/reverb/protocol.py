"""Pusher Protocol v7 frame builders."""

from __future__ import annotations

import json
from typing import Any


def build_connection_established(*, socket_id: str, activity_timeout: int) -> str:
    return json.dumps(
        {
            "event": "pusher:connection_established",
            "data": json.dumps(
                {
                    "socket_id": socket_id,
                    "activity_timeout": activity_timeout,
                }
            ),
        }
    )


def build_subscription_succeeded(*, channel: str, presence_data: dict[str, Any] | None) -> str:
    body: dict[str, Any] = {
        "event": "pusher_internal:subscription_succeeded",
        "channel": channel,
    }
    if presence_data is not None:
        body["data"] = json.dumps(presence_data)
    else:
        body["data"] = "{}"
    return json.dumps(body)


def build_error(*, code: int, message: str) -> str:
    return json.dumps(
        {
            "event": "pusher:error",
            "data": json.dumps({"code": code, "message": message}),
        }
    )


def build_pong() -> str:
    return json.dumps({"event": "pusher:pong", "data": "{}"})


def build_event_frame(*, channel: str, event: str, data: dict[str, Any]) -> str:
    return json.dumps(
        {
            "event": event,
            "channel": channel,
            "data": json.dumps(data),
        }
    )


def build_member_added(*, channel: str, user_id: str, user_info: dict[str, Any]) -> str:
    return json.dumps(
        {
            "event": "pusher_internal:member_added",
            "channel": channel,
            "data": json.dumps({"user_id": user_id, "user_info": user_info}),
        }
    )


def build_member_removed(*, channel: str, user_id: str) -> str:
    return json.dumps(
        {
            "event": "pusher_internal:member_removed",
            "channel": channel,
            "data": json.dumps({"user_id": user_id}),
        }
    )


__all__ = [
    "build_connection_established",
    "build_error",
    "build_event_frame",
    "build_member_added",
    "build_member_removed",
    "build_pong",
    "build_subscription_succeeded",
]
