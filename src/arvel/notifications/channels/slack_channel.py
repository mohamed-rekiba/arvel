"""Slack incoming-webhook notification channel."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from httpx import HTTPError

from arvel.notifications.contracts import NotificationChannel
from arvel.notifications.exceptions import NotificationChannelError

if TYPE_CHECKING:
    from typing import Any

    from arvel.notifications.notification import Notification, SlackMessage


def _slack_json(message: SlackMessage) -> dict[str, object]:
    payload: dict[str, object] = {}
    if message.text:
        payload["text"] = message.text
    if message.blocks:
        payload["blocks"] = message.blocks
    return payload


class SlackChannel(NotificationChannel):
    """Posts JSON payloads to a Slack incoming webhook URL."""

    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    async def deliver(self, notifiable: Any, notification: Notification) -> None:
        slack_message = notification.to_slack(notifiable)
        payload = _slack_json(slack_message)
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self._webhook_url, json=payload)
                response.raise_for_status()
        except HTTPError as exc:
            raise NotificationChannelError("slack", str(exc)) from exc
        except Exception as exc:
            raise NotificationChannelError("slack", str(exc)) from exc
