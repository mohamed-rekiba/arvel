"""Notification channel and notifiable edge paths."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, cast

import pytest
from arvel.notifications import notification_job as notification_job_module
from arvel.notifications.channels import log_channel as log_channel_module
from arvel.notifications.channels.broadcast_channel import BroadcastChannel
from arvel.notifications.channels.log_channel import LogChannel
from arvel.notifications.channels.mail_channel import MailChannel
from arvel.notifications.manager import NotificationManager
from arvel.notifications.notifiable import Notifiable
from arvel.notifications.notification import Notification

if TYPE_CHECKING:
    from arvel.mail.mailer import Mailer


class _Notification(Notification):
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def via(self, notifiable: Any) -> list[str]:
        _ = notifiable
        return ["broadcast"]

    def to_broadcast(self, notifiable: Any) -> dict[str, Any]:
        _ = notifiable
        return self._payload


class _Manager(NotificationManager):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def send(self, notifiable: object, notification: Notification) -> None:
        _ = (notifiable, notification)
        self.calls.append("send")

    async def send_via_queue(self, notifiable: object, notification: Notification) -> None:
        _ = (notifiable, notification)
        self.calls.append("queue")

    async def send_now(self, notifiable: object, notification: Notification) -> None:
        _ = (notifiable, notification)
        self.calls.append("now")


class _User(Notifiable):
    def __init__(self, manager: _Manager) -> None:
        self.notification_manager = manager


async def test_broadcast_channel_skips_invalid_specs() -> None:
    channel = BroadcastChannel()
    user = object()

    await channel.send(user, _Notification({}))
    await channel.send(user, _Notification({"channels": "orders", "data": {}}))
    await channel.send(user, _Notification({"channels": ["orders"], "data": []}))


async def test_log_channel_swallows_logger_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    class Logger:
        def info(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("logger down")

    monkeypatch.setattr(log_channel_module, "logger", Logger())

    await LogChannel().send(object(), _Notification({}))


async def test_mail_channel_skips_when_notification_has_no_mail() -> None:
    channel = MailChannel(cast("Mailer", object()))

    await channel.send(object(), _Notification({}))


def test_notification_job_resolves_classes_from_registry() -> None:
    from arvel.notifications.notifiable import NotifiableRegistry
    from arvel.notifications.notification import NotificationRegistry

    notifiable_key = f"{_User.__module__}.{_User.__qualname__}"
    notification_key = f"{_Notification.__module__}.{_Notification.__qualname__}"

    assert NotifiableRegistry[notifiable_key] is _User
    assert NotificationRegistry[notification_key] is _Notification


async def test_notifiable_uses_injected_manager() -> None:
    manager = _Manager()
    user = _User(manager)
    notification = _Notification({})

    await user.notify(notification)
    await user.notify_now(notification)

    assert manager.calls == ["send", "now"]


async def test_notification_job_refetches_notifiables() -> None:
    refetch = cast(
        "Callable[[type, str], Awaitable[object]]",
        object.__getattribute__(notification_job_module, "_refetch_notifiable"),
    )

    class User:
        @classmethod
        async def find(cls, user_id: int | str) -> User | None:
            if user_id == 1:
                return cls()
            return None

    assert isinstance(await refetch(User, "1"), User)
    with pytest.raises(LookupError, match="was not found"):
        await refetch(User, "missing")


async def test_notification_job_requires_find_method() -> None:
    refetch = cast(
        "Callable[[type, str], Awaitable[object]]",
        object.__getattribute__(notification_job_module, "_refetch_notifiable"),
    )

    class MissingFind:
        pass

    with pytest.raises(TypeError, match="must define find"):
        await refetch(MissingFind, "1")
