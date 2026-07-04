"""arvel.notifications — multi-channel notifications on **apprise** (mandated engine).

A ``Notification`` declares its channels via ``via(notifiable)``; the manager fans out:
``mail`` → the Mail manager, ``database`` → a persisted ``DatabaseNotification`` row (``to_array``
payload), and any other channel → a real ``apprise.Apprise`` client (G4 — apprise drives
Slack/Discord/Telegram/… via ``apprise_urls``). apprise + the DB model are imported lazily.
Grounded in knowledge/port/16-managers.md.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from arvel.queue import Job

if TYPE_CHECKING:
    from arvel.mail import Mailable
    from arvel.notifications.database import DatabaseNotification as DatabaseNotification


class Notification:
    """Base notification: override ``via`` + the per-channel ``to_*`` builders."""

    def via(self, notifiable: Any) -> list[str]:
        return ["mail"]

    def to_mail(self, notifiable: Any) -> Mailable:
        raise NotImplementedError(f"{type(self).__name__} must implement to_mail()")

    def to_array(self, notifiable: Any) -> dict[str, Any]:
        return {}

    def apprise_urls(self, notifiable: Any) -> list[str]:
        return []


class SendQueuedNotification(Job):
    """Worker job that delivers a notification enqueued via the ShouldQueue rail.

    The notification is stored as a JSON-safe ``{class, state}`` view (``encode_instance``), not the
    live object, so the job survives serialization across a **real broker** — a plain Notification is
    not a Model, so without this it hits ``msgspec`` "unsupported type". The notifiable is a Model, so
    the job's own ``serialize_instance`` already (class, pk)-refs it."""

    def __init__(
        self, notifiable: Any, notification: Notification, channels: list[str] | None = None
    ) -> None:
        from arvel.queue import encode_instance

        self.notifiable = notifiable
        self.notification = encode_instance(notification)  # serializable repr (not the live object)
        # one job per channel (None = all of via()), so retrying a failed mail job can't double-store
        # an already-delivered database channel.
        self.channels = channels

    async def handle(self) -> dict[str, Any]:
        from arvel.kernel import app
        from arvel.queue import decode_instance

        manager: NotificationManager = app().make("notifications")
        notification = cast("Notification", await decode_instance(self.notification))
        return await manager.send_now(self.notifiable, notification, channels=self.channels)


class NotificationManager:
    """Fans a notification out across its channels."""

    def __init__(self, app: Any = None) -> None:
        self.app = app

    def apprise(self) -> Any:
        import apprise

        return apprise.Apprise()

    def _mailer(self) -> Any:
        if self.app is not None and hasattr(self.app, "bound") and self.app.bound("mail"):
            return self.app.make("mail")
        from arvel.mail import MailManager

        return MailManager(self.app)

    async def send(self, notifiable: Any, notification: Notification) -> dict[str, Any]:
        """Send ``notification`` — inline, or onto the queue when it's ``ShouldQueue`` and a
        queue is bound (mirrors the mail/events ShouldQueue rail)."""
        from arvel.events import ShouldQueue

        app = self.app
        if (
            isinstance(notification, ShouldQueue)
            and app is not None
            and hasattr(app, "bound")
            and app.bound("queue")
        ):
            queue = app.make("queue")
            for channel in notification.via(notifiable):
                await queue.push_instance(
                    SendQueuedNotification(notifiable, notification, channels=[channel])
                )
            return {"queued": True}
        return await self.send_now(notifiable, notification)

    async def send_now(
        self,
        notifiable: Any,
        notification: Notification,
        channels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fan out immediately, bypassing the queue rail — across all of ``via()``, or only the
        given ``channels`` slice (the per-channel worker path)."""
        results: dict[str, Any] = {}
        for channel in channels if channels is not None else notification.via(notifiable):
            results[channel] = await self._dispatch(channel, notifiable, notification)
        return results

    async def _store_database(self, notifiable: Any, notification: Notification) -> Any:
        """Persist a row in the ``notifications`` table (Laravel ``database`` channel). When no DB is
        bound (e.g. an on-demand send, or tests without a connection) gracefully return the ``to_array``
        payload instead of persisting — the channel still reports a result, nothing is silently lost."""
        data = notification.to_array(notifiable)
        from arvel.kernel import app, has_application

        if not (has_application() and app().bound("db")):
            return data
        from arvel.notifications.database import DatabaseNotification

        key_name = getattr(notifiable, "__primary_key__", "id")
        return await DatabaseNotification.create(
            type=type(notification).__name__,
            notifiable_type=type(notifiable).__name__,
            notifiable_id=str(getattr(notifiable, key_name, None)),
            data=data,
            read_at=None,
        )

    @staticmethod
    def _route(notifiable: Any, channel: str, default: Any) -> Any:
        """The recipient/route for ``channel`` — a notifiable's ``route_notification_for(channel)``
        (Laravel ``routeNotificationFor``) when it defines one (e.g. on-demand sends), else ``default``."""
        fn = getattr(notifiable, "route_notification_for", None)
        if callable(fn):
            routed = fn(channel)
            if routed is not None:
                return routed
        return default

    async def _dispatch(self, channel: str, notifiable: Any, notification: Notification) -> Any:
        if channel == "mail":
            recipient = self._route(notifiable, "mail", notifiable)
            return await self._mailer().to(recipient).send(notification.to_mail(notifiable))
        if channel == "database":
            return await self._store_database(notifiable, notification)
        client = self.apprise()
        urls = self._route(notifiable, channel, None) or notification.apprise_urls(notifiable)
        for url in urls:
            client.add(url)
        body = str(notification.to_array(notifiable) or type(notification).__name__)
        return await client.async_notify(body=body)


def _resolve_manager() -> NotificationManager:
    from arvel.kernel import app, has_application

    if has_application() and app().bound("notifications"):
        return cast("NotificationManager", app().make("notifications"))
    return NotificationManager()


class Notifiable:
    """Mixin for a notifiable model: ``await user.notify(SomeNotification())`` plus retrieval of the
    rows the ``database`` channel stored (``notifications`` / ``unread_notifications`` /
    ``mark_all_notifications_as_read``), keyed by this model's class name + primary key."""

    async def notify(self, notification: Notification) -> dict[str, Any]:
        return await _resolve_manager().send(self, notification)

    def _notification_query(self) -> Any:
        """Base query for this notifiable's stored notifications, newest first."""
        from arvel.notifications.database import DatabaseNotification

        me: Any = self
        key_name = getattr(me, "__primary_key__", "id")
        return DatabaseNotification.where(
            notifiable_type=type(self).__name__,
            notifiable_id=str(getattr(me, key_name, None)),
        ).order_by("created_at", "desc")

    async def notifications(self) -> list[Any]:
        """All stored notifications for this notifiable, newest first."""
        rows: list[Any] = await self._notification_query().get()
        return rows

    async def unread_notifications(self) -> list[Any]:
        """Stored notifications that haven't been read (``read_at`` is null)."""
        rows: list[Any] = await self._notification_query().where_null("read_at").get()
        return rows

    async def mark_all_notifications_as_read(self) -> None:
        """Stamp every unread notification as read."""
        for note in await self.unread_notifications():
            await note.mark_as_read()


class AnonymousNotifiable:
    """An on-demand recipient with no stored model (Laravel ``Notification::route(...)``):

        await AnonymousNotifiable().route("mail", "ops@acme.test").notify(AlertRaised(incident))

    Each ``route(channel, route)`` sets where that channel delivers; the manager reads it via
    ``route_notification_for`` (mail → an address, apprise channels → a URL or list of URLs)."""

    def __init__(self) -> None:
        self._routes: dict[str, Any] = {}

    def route(self, channel: str, route: Any) -> AnonymousNotifiable:
        self._routes[channel] = route
        return self

    def route_notification_for(self, channel: str) -> Any:
        return self._routes.get(channel)

    async def notify(self, notification: Notification) -> dict[str, Any]:
        return await _resolve_manager().send(self, notification)


def __getattr__(name: str) -> Any:
    # DatabaseNotification pulls in arvel.database (SQLAlchemy); resolve lazily to keep import light.
    if name == "DatabaseNotification":
        from arvel.notifications.database import DatabaseNotification

        return DatabaseNotification
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AnonymousNotifiable",
    "DatabaseNotification",
    "Notifiable",
    "Notification",
    "NotificationManager",
    "SendQueuedNotification",
]
