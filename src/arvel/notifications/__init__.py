"""arvel.notifications — multi-channel notifications on **apprise** (mandated engine).

A ``Notification`` declares its channels via ``via(notifiable)``; the manager fans out:
``mail`` → the Mail manager, ``database`` → a persisted ``DatabaseNotification`` row (``to_array``
payload), and any other channel → a real ``apprise.Apprise`` client (G4 — apprise drives
Slack/Discord/Telegram/… via ``apprise_urls``). apprise + the DB model are imported lazily.
Grounded in knowledge/port/16-managers.md.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from arvel.broadcasting import PrivateChannel
from arvel.events import ShouldBroadcast
from arvel.kernel import Settings
from arvel.queue import Job
from arvel.support.manager import Manager

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from arvel.mail import Mailable
    from arvel.notifications.database import DatabaseNotification as DatabaseNotification


class NotificationSettings(Settings):
    """Typed view over the ``notifications`` config section — the channel used when the manager's
    ``driver()`` is resolved with no explicit name (channels are otherwise always named via
    ``via()``, so this rarely matters in practice)."""

    __config_key__ = "notifications"
    default: str = "mail"


@dataclass(frozen=True)
class NotificationSending:
    """Fired before a channel's send; a listener returning ``False`` vetoes that channel (the
    notification's own ``should_send`` still runs first)."""

    notifiable: Any
    notification: Notification
    channel: str


@dataclass(frozen=True)
class NotificationSent:
    """Fired after a channel's send completes, carrying its result."""

    notifiable: Any
    notification: Notification
    channel: str
    response: Any


@dataclass
class AppriseMessage:
    """A title/body message for the push channels (Slack/Discord/Telegram/…). ``notify_type`` is
    one of ``info``/``success``/``warning``/``failure`` (drives the target's colour/icon)."""

    body: str
    title: str = ""
    notify_type: str = "info"


class Notification:
    """Base notification: override ``via`` + the per-channel ``to_*`` builders."""

    def via(self, notifiable: Any) -> list[str]:
        return ["mail"]

    def to_mail(self, notifiable: Any) -> Mailable:
        raise NotImplementedError(f"{type(self).__name__} must implement to_mail()")

    def to_array(self, notifiable: Any) -> dict[str, Any]:
        return {}

    def to_broadcast(self, notifiable: Any) -> dict[str, Any]:
        """The payload for the ``broadcast`` channel — defaults to
        ``to_array()``."""
        return self.to_array(notifiable)

    def apprise_urls(self, notifiable: Any) -> list[str]:
        return []

    def to_apprise(self, notifiable: Any) -> AppriseMessage:
        """The message for the push channels — override for a real title/body. The default derives
        them from ``to_array()``: a ``subject``/``title`` key becomes the title, a
        ``body``/``message``/``greeting`` key the body, otherwise the payload renders as
        ``key: value`` lines instead of a raw stringified dict."""
        data = self.to_array(notifiable)
        title = str(data.get("subject") or data.get("title") or type(self).__name__)
        body = data.get("body") or data.get("message") or data.get("greeting")
        if body is None:
            body = "\n".join(f"{key}: {value}" for key, value in data.items())
        return AppriseMessage(body=str(body) or type(self).__name__, title=title)

    def should_send(self, notifiable: Any, channel: str) -> bool:
        """Consulted before EACH channel send; ``False`` skips that channel silently (no error, no
        result entry) while the rest of ``via()`` still runs. Override for per-notifiable/per-channel
        opt-out (e.g. a muted digest)."""
        return True

    def middleware(self) -> list[Any]:
        """Job middleware this notification's queued send runs through — e.g. ``[RateLimited(limiter,
        key=..., max_attempts=5, decay_seconds=60)]`` (``arvel.queue.middleware``). Empty by default;
        a subclass overrides to declare per-send middleware, resolving any collaborator (a limiter,
        say) fresh from the container rather than storing it on ``self`` — an attribute has to
        survive ``encode_instance``/serialization across the queue, and a live limiter can't.

        **Queued-rail only.** This is consulted by :meth:`SendQueuedNotification.middleware`, which
        the worker calls before running the job — an inline send (not ``ShouldQueue``, or no queue
        bound) never builds a job, so this never runs and no throttle applies there. That's the
        reference's behavior, not a gap: don't fake a synchronous inline throttle to "fix" it."""
        return []


class BroadcastNotification(ShouldBroadcast):
    """The event a notification's ``broadcast`` channel sends: ``to_broadcast()``'s payload, on the notifiable's channel."""

    def __init__(self, notifiable: Any, notification: Notification) -> None:
        self.notifiable = notifiable
        self.notification = notification

    def broadcast_on(self) -> list[Any]:
        channel = getattr(self.notifiable, "receives_broadcast_notifications_on", None)
        if callable(channel):
            return [channel()]
        key_name = getattr(self.notifiable, "__primary_key__", "id")
        pk = getattr(self.notifiable, key_name, "")
        return [PrivateChannel(f"{type(self.notifiable).__name__}.{pk}")]

    def broadcast_as(self) -> str:
        return type(self.notification).__name__

    def broadcast_with(self) -> dict[str, Any]:
        return self.notification.to_broadcast(self.notifiable)


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

    def middleware(self) -> list[Any]:
        """Surfaces the wrapped notification's own :meth:`Notification.middleware` into the
        EXISTING job-middleware onion (``Job.middleware()`` -> ``worker._wrap_with_middleware`` ->
        ``Pipeline`` — E14, unchanged) so a declared ``RateLimited``/etc. runs there. No parallel
        throttle: this is the entire integration.

        The worker calls a job's ``middleware()`` SYNCHRONOUSLY, before the async ``handle()`` above
        decodes ``self.notification`` — so this can't call ``self.notification.middleware()`` (still
        the JSON-safe ``encode_instance`` dict here, not the live object) or ``await`` a decode.
        Reconstruct synchronously instead: bypass ``__init__`` and restore ``__dict__`` straight from
        the encoded state, same shape as :func:`~arvel.queue.decode_instance` minus its async
        model-ref rehydration. So ``middleware()`` sees only JSON-plain state — a Model attribute is
        still a ``{id}`` ref, a ``datetime`` a dict — it must key on a plain scalar the notification
        captured in ``__init__``, never on ``self.<model>.id`` (that only works in ``handle()``,
        which runs after rehydration). The notification's own ``middleware()`` then builds e.g.
        ``RateLimited`` fresh (resolving its limiter from the container), so nothing live has to
        have survived serialization."""
        from arvel.queue import _load  # pyright: ignore[reportPrivateUsage]

        cls = _load(str(self.notification["__class__"]))
        notification = cls.__new__(cls)
        notification.__dict__.update(cast("dict[str, Any]", self.notification["__state__"]))
        return cast("list[Any]", notification.middleware())


class _Channel:
    """A single named channel driver: wraps the async ``send(channel, notifiable, notification)``
    closure a ``create_<name>_driver`` builds — the closure (not a manager back-reference) is what
    lets it reach the manager's own ``_route``/``_mailer``/etc. helpers without a cross-class
    private-attribute reach-around."""

    def __init__(self, send: Callable[[str, Any, Notification], Awaitable[Any]]) -> None:
        self._send = send

    async def send(self, channel: str, notifiable: Any, notification: Notification) -> Any:
        return await self._send(channel, notifiable, notification)


class NotificationManager(Manager):
    """Fans a notification out across its channels — one ``support.Manager`` driver per channel
    (``mail``/``database``/``broadcast``, else the ``apprise`` catch-all), so a custom channel is
    just ``extend(name, creator)`` like any other manager."""

    def default_driver(self) -> str:
        return self._settings(NotificationSettings).default

    def create_mail_driver(self) -> _Channel:
        async def _send(channel: str, notifiable: Any, notification: Notification) -> Any:
            recipient = self._route(notifiable, "mail", notifiable)
            return await self._mailer().to(recipient).send(notification.to_mail(notifiable))

        return _Channel(_send)

    def create_database_driver(self) -> _Channel:
        async def _send(channel: str, notifiable: Any, notification: Notification) -> Any:
            return await self._store_database(notifiable, notification)

        return _Channel(_send)

    def create_broadcast_driver(self) -> _Channel:
        async def _send(channel: str, notifiable: Any, notification: Notification) -> Any:
            await self._broadcaster().broadcast(BroadcastNotification(notifiable, notification))
            return True

        return _Channel(_send)

    def create_apprise_driver(self) -> _Channel:
        async def _send(channel: str, notifiable: Any, notification: Notification) -> Any:
            client = self.apprise()
            urls = self._route(notifiable, channel, None) or notification.apprise_urls(notifiable)
            for url in urls:
                client.add(url)
            message = notification.to_apprise(notifiable)
            return await client.async_notify(
                body=message.body, title=message.title, notify_type=message.notify_type
            )

        return _Channel(_send)

    def apprise(self) -> Any:
        import apprise

        return apprise.Apprise()

    def _mailer(self) -> Any:
        if self.app is not None and hasattr(self.app, "bound") and self.app.bound("mail"):
            return self.app.make("mail")
        from arvel.mail import MailManager

        return MailManager(self.app)

    def _events(self) -> Any:
        """The bound event dispatcher, else ``None`` (soft-coupled — no-op without an app)."""
        app = self.app
        if app is not None and hasattr(app, "bound") and app.bound("events"):
            return app.make("events")
        return None

    async def _after_commit(self, callback: Callable[[], Awaitable[Any]]) -> Any:
        """Route ``callback`` through the events after-commit buffer — the SAME seam
        ``QueueManager._defer_to_commit``/mail's ``PendingMail`` use: buffered while a transaction
        is open (dropped on rollback), run immediately outside one/without an events dispatcher."""
        events = self._events()
        if events is not None:
            return await events.after_commit(callback)
        return await callback()

    async def send(self, notifiable: Any, notification: Notification) -> dict[str, Any]:
        """Send ``notification`` — inline, or onto the queue when it's ``ShouldQueue`` and a
        queue is bound (mirrors the mail/events ShouldQueue rail). Each channel's enqueue rides
        the after-commit seam, same as a queued job."""
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
                job = SendQueuedNotification(notifiable, notification, channels=[channel])
                await self._after_commit(functools.partial(queue.push_instance, job))
            return {"queued": True}
        return await self.send_now(notifiable, notification)

    async def later(
        self, delay: float, notifiable: Any, notification: Notification
    ) -> dict[str, Any]:
        """Queue ``notification`` to send after ``delay`` seconds via the queue's durable
        delayed-dispatch path (``dispatch_after``) — regardless of ``ShouldQueue``, one job per
        channel like :meth:`send`. Falls back to an immediate send when no queue is bound."""
        app = self.app
        if not (app is not None and hasattr(app, "bound") and app.bound("queue")):
            return await self.send_now(notifiable, notification)
        queue = app.make("queue")
        for channel in notification.via(notifiable):
            job = SendQueuedNotification(notifiable, notification, channels=[channel])
            await self._after_commit(functools.partial(queue.dispatch_after, delay, job))
        return {"queued": True}

    async def send_now(
        self,
        notifiable: Any,
        notification: Notification,
        channels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fan out immediately, bypassing the queue rail — across all of ``via()``, or only the
        given ``channels`` slice (the per-channel worker path). ``should_send(notifiable, channel)``
        is consulted first; ``False`` skips that channel silently — no result entry, no error — while
        the rest of the channels still send. When an events dispatcher is bound, each channel also
        fires ``NotificationSending`` first (a listener returning ``False`` vetoes just that channel,
        same silent skip) and ``NotificationSent`` after a successful send."""
        events = self._events()
        results: dict[str, Any] = {}
        for channel in channels if channels is not None else notification.via(notifiable):
            if not notification.should_send(notifiable, channel):
                continue
            if events is not None:
                veto = await events.until(NotificationSending(notifiable, notification, channel))
                if veto is False:
                    continue
            result = await self._dispatch(channel, notifiable, notification)
            results[channel] = result
            if events is not None:
                await events.dispatch(NotificationSent(notifiable, notification, channel, result))
        return results

    async def _store_database(self, notifiable: Any, notification: Notification) -> Any:
        """Persist a row in the ``notifications`` table. When no DB is
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
        when it defines one (e.g. on-demand sends), else ``default``."""
        fn = getattr(notifiable, "route_notification_for", None)
        if callable(fn):
            routed = fn(channel)
            if routed is not None:
                return routed
        return default

    def _broadcaster(self) -> Any:
        """The bound ``broadcast`` manager, else a fresh in-process one (mirrors ``_mailer()``'s
        fallback — e.g. an on-demand send with no bound app)."""
        if self.app is not None and hasattr(self.app, "bound") and self.app.bound("broadcast"):
            return self.app.make("broadcast")
        from arvel.broadcasting import BroadcastManager

        return BroadcastManager(self.app)

    async def _dispatch(self, channel: str, notifiable: Any, notification: Notification) -> Any:
        """Resolve ``channel`` to a driver — the three built-ins or an ``extend()``-ed custom
        channel dispatch by their own name; anything else falls through to the ``apprise``
        catch-all — and run its ``send()``."""
        driver_name = (
            channel
            if channel in ("mail", "database", "broadcast") or channel in self._creators
            else "apprise"
        )
        return await self.driver(driver_name).send(channel, notifiable, notification)


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
        """Stamp every unread notification as read in ONE mass ``UPDATE`` — not a per-row
        fetch-then-save loop."""
        from arvel.dates import Date

        await self._notification_query().where_null("read_at").update({"read_at": Date.now()})


class AnonymousNotifiable:
    """An on-demand recipient with no stored model:

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
    "AppriseMessage",
    "BroadcastNotification",
    "DatabaseNotification",
    "Notifiable",
    "Notification",
    "NotificationManager",
    "NotificationSending",
    "NotificationSent",
    "NotificationSettings",
    "SendQueuedNotification",
]
