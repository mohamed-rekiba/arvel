"""NotificationJob — dispatches a queued notification via the notification manager."""

from __future__ import annotations

import inspect
from typing import Any

from arvel.notifications.exceptions import UnregisteredNotificationClassError
from arvel.queue.job import Job


class NotificationJob(Job):
    """Delivers a notification asynchronously through the queue.

    Fields mirror the ShouldQueue contract: the notifiable object is referenced by
    class name + ID so the job is serializable; the notification is referenced by
    class name so it can be reconstructed on the worker side.

    Both classes are resolved from allowlist registries populated at class
    definition — never by importing the dotted path from the queue payload. That
    keeps a tampered payload from triggering arbitrary module imports.
    """

    notifiable_id: str
    notifiable_class: str
    notification_class: str

    async def handle(self) -> None:
        from arvel.facades.notification import Notification
        from arvel.notifications.notifiable import NotifiableRegistry
        from arvel.notifications.notification import NotificationRegistry

        notifiable_cls = _resolve(NotifiableRegistry, self.notifiable_class, "notifiable")
        notification_cls = _resolve(NotificationRegistry, self.notification_class, "notification")
        notifiable = await _refetch_notifiable(notifiable_cls, self.notifiable_id)
        notification = notification_cls()
        await Notification.send_now(notifiable, notification)


def _resolve(registry: dict[str, type[Any]], key: str, kind: str) -> type[Any]:
    cls = registry.get(key)
    if cls is None:
        raise UnregisteredNotificationClassError(kind, key)
    return cls


async def _refetch_notifiable(notifiable_cls: type, notifiable_id: str) -> Any:
    finder = getattr(notifiable_cls, "find", None)
    if not callable(finder):
        msg = f"{notifiable_cls.__qualname__} must define find() for queued notifications."
        raise TypeError(msg)

    lookup_id: int | str = int(notifiable_id) if notifiable_id.isdecimal() else notifiable_id
    result = finder(lookup_id)
    if inspect.isawaitable(result):
        result = await result
    if result is None:
        msg = f"{notifiable_cls.__qualname__}({notifiable_id!r}) was not found."
        raise LookupError(msg)
    return result


__all__ = ["NotificationJob"]
