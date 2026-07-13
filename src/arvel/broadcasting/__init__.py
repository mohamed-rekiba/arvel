"""arvel.broadcasting — broadcast ``ShouldBroadcast`` events to realtime channels.

The event dispatcher routes a ``ShouldBroadcast`` event to the bound ``broadcast`` manager,
which sends it on the event's channels. Core ships a ``log`` driver (records, no network) for
dev/test and a ``redis`` driver (publishes over story-06's redis facade) — the realtime
websocket/Reverb transport is a driver extra. Channels + channel-authorization callbacks
(``Broadcast.channel(pattern, callback)``) live here too; the ``/broadcasting/auth`` HTTP endpoint
that resolves the authenticated user does **not** — it lives in ``arvel.routing`` (see that
module's ``broadcasting_auth``), because broadcasting sits below ``arvel.auth`` in the module DAG
(G1) and must never import it. Grounded in knowledge/port/11-events.md.
"""

from __future__ import annotations

import inspect
import re
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, cast

from arvel.kernel import Settings
from arvel.support.manager import Manager

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Self


class BroadcastingSettings(Settings):
    """Typed, validated view over the ``broadcasting`` config section (DR-0016)."""

    __config_key__ = "broadcasting"
    default: str = "log"  # driver name (open registry → str)


def channels_for(event: Any) -> list[str]:
    """The channel names an event broadcasts on (its ``broadcast_on()``), or ``[]``.

    ``broadcast_on()`` may return plain strings or typed :class:`Channel`/:class:`PrivateChannel`/
    :class:`PresenceChannel` instances — ``str()`` on each yields the wire name either way (a
    ``Channel`` is used as-is; ``PrivateChannel``/``PresenceChannel`` get the Pusher-protocol
    ``private-``/``presence-`` prefix)."""
    getter = getattr(event, "broadcast_on", None)
    if not callable(getter):
        return []
    return [str(c) for c in cast("list[Any]", getter())]


def event_name(event: Any) -> str:
    """The wire name for an event (its ``broadcast_as()``, else the class name)."""
    getter = getattr(event, "broadcast_as", None)
    return str(getter()) if callable(getter) else type(event).__name__


def broadcast_payload(event: Any) -> dict[str, Any]:
    """The event's broadcast data payload — its ``broadcast_with()`` if defined, else ``{}``."""
    getter = getattr(event, "broadcast_with", None)
    if not callable(getter):
        return {}
    payload: Any = getter()
    return dict(cast("dict[str, Any]", payload)) if isinstance(payload, dict) else {}


def except_socket_id(event: Any) -> str | None:
    """The socket id ``to_others()`` excluded on ``event`` (see :class:`InteractsWithSockets`),
    else ``None`` when the event never called it."""
    return cast("str | None", getattr(event, "_except_socket_id", None))


# --- channels (Pusher-protocol wire names) ---------------------------------


class Channel:
    """A public broadcast channel — its wire name is used as-is."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.name!r})"


class PrivateChannel(Channel):
    """A private channel: wire name gets the ``private-`` prefix; subscribing requires the
    ``/broadcasting/auth`` endpoint to authorize the requesting user against a registered callback."""

    def __str__(self) -> str:
        return f"private-{self.name}"


class PresenceChannel(Channel):
    """A presence channel: wire name gets the ``presence-`` prefix; authorization returns the
    joining member's data (a ``dict``) rather than a plain bool."""

    def __str__(self) -> str:
        return f"presence-{self.name}"


_PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")


def _compile_channel_pattern(pattern: str) -> re.Pattern[str]:
    """Compile a channel-authorization pattern (e.g. ``chat.{id}``) into an anchored regex with one
    capture group per ``{placeholder}`` — literal segments are ``re.escape``d."""
    parts: list[str] = []
    last = 0
    for match in _PLACEHOLDER_RE.finditer(pattern):
        parts.append(re.escape(pattern[last : match.start()]))
        parts.append(r"([^./]+)")
        last = match.end()
    parts.append(re.escape(pattern[last:]))
    return re.compile(f"^{''.join(parts)}$")


# --- sockets: to_others()/broadcast_when() ---------------------------------

_socket_id: ContextVar[str | None] = ContextVar("arvel_broadcast_socket_id", default=None)


def current_socket_id() -> str | None:
    """The socket id bound for the current request/task (see :func:`bind_socket_id`), else
    ``None``."""
    return _socket_id.get()


def bind_socket_id(value: str | None) -> None:
    """Bind the current request's socket id (its ``X-Socket-ID`` header) so an event's
    ``to_others()`` can read it without broadcasting importing ``arvel.http`` (http sits above
    broadcasting in the DAG). An app wires this at the point it reads the header — e.g.
    ``bind_socket_id(request.header("X-Socket-ID"))`` before dispatching an event."""
    _socket_id.set(value)


class InteractsWithSockets:
    """Mixin for a ``ShouldBroadcast`` event: exclude the triggering socket (``to_others()``) or
    suppress the broadcast under a condition (``broadcast_when()``)."""

    _except_socket_id: str | None = None
    _when: Callable[[], bool] | None = None

    def to_others(self, socket_id: str | None = None) -> Self:
        """Exclude a socket from delivery: an explicit ``socket_id``, else the bound current one
        (:func:`bind_socket_id`)."""
        self._except_socket_id = socket_id if socket_id is not None else current_socket_id()
        return self

    def broadcast_when(self, condition: Callable[[], bool]) -> Self:
        """Only broadcast when ``condition()`` is true at send time."""
        self._when = condition
        return self

    def should_broadcast(self) -> bool:
        """Whether this event should broadcast at all — ``broadcast_when()``'s condition, else
        ``True`` (checked once, centrally, in ``BroadcastManager.broadcast``)."""
        return self._when() if self._when is not None else True

    def consume_broadcast_condition(self) -> None:
        """Drop the one-shot ``broadcast_when()`` closure after it's been evaluated — the public
        seam the dispatcher calls once at dispatch (the closure can't serialize onto the broker).
        A public method so the events layer never has to reach into this mixin's private ``_when``."""
        self._when = None


def accepts(payload: dict[str, Any], socket_id: str | None) -> bool:
    """Whether a subscriber holding ``socket_id`` should accept a decoded broadcast ``payload`` —
    ``False`` when ``payload["except_socket_id"]`` names this exact socket (the receiving side of
    ``to_others()``): the subscriber that triggered the event skips its own echo; every other
    subscriber still accepts it."""
    excluded = payload.get("except_socket_id")
    return not (socket_id is not None and excluded == socket_id)


class Broadcaster:
    """Base broadcaster: override ``broadcast``."""

    async def broadcast(self, event: Any) -> None:
        raise NotImplementedError


#: How many recent broadcasts the log driver retains — it's a dev/test recorder AND the default
#: driver, so an unconfigured production app that keeps dispatching ShouldBroadcast events must not
#: grow ``sent`` without bound. Keep only the most recent N.
LOG_BROADCASTER_HISTORY = 1000


class LogBroadcaster(Broadcaster):
    """A no-network broadcaster that records each broadcast (dev/test default).

    ``sent`` stays a plain ``list`` (tests read/compare it directly), but it's **bounded** to the
    most recent ``history`` entries so an unconfigured production app can't leak memory."""

    def __init__(self, history: int = LOG_BROADCASTER_HISTORY) -> None:
        self.sent: list[tuple[str, list[str], Any]] = []
        self._history = history

    async def broadcast(self, event: Any) -> None:
        self.sent.append((event_name(event), channels_for(event), event))
        if len(self.sent) > self._history:  # drop the oldest so growth stays bounded
            del self.sent[0 : len(self.sent) - self._history]


# The redis channel prefix each broadcast is published under — part of the publish wire contract, so
# a subscriber (the websocket relay) reads the same one rather than re-deriving it.
CHANNEL_PREFIX = "arvel.broadcasting."


class RedisBroadcaster(Broadcaster):
    """Publishes each broadcast event as one JSON message per channel via the container-bound
    ``redis`` connection (story-06's facade — ``RedisConnection.publish``), resolved dynamically
    through the app container rather than importing ``arvel.cache`` directly: broadcasting sits
    below ``arvel.cache`` in the module DAG (G1), so a static import would be a back-edge."""

    _CHANNEL_PREFIX = CHANNEL_PREFIX

    def __init__(self, app: Any) -> None:
        if app is None:
            raise RuntimeError(
                "The 'redis' broadcast driver needs a bound app (app.make('redis'))."
            )
        self._app = app

    async def broadcast(self, event: Any) -> None:
        import json

        redis = self._app.make("redis")
        body = json.dumps(
            {
                "event": event_name(event),
                "data": broadcast_payload(event),
                "except_socket_id": except_socket_id(event),
            }
        )
        for channel in channels_for(event):
            await redis.publish(f"{self._CHANNEL_PREFIX}{channel}", body)


class BroadcastManager(Manager):
    """Resolves broadcast drivers by config and sends events to the active one; also holds the
    channel-authorization registry (``Broadcast.channel(pattern, callback)``)."""

    def __init__(self, app: Any = None) -> None:
        super().__init__(app)
        self._channels: list[tuple[re.Pattern[str], Callable[..., Any]]] = []

    def default_driver(self) -> str:
        return BroadcastingSettings().default  # auto-loads + validates config("broadcasting")

    def create_log_driver(self) -> LogBroadcaster:
        return LogBroadcaster()

    def create_redis_driver(self) -> RedisBroadcaster:
        return RedisBroadcaster(self.app)

    async def broadcast(self, event: Any) -> None:
        should = getattr(event, "should_broadcast", None)
        if callable(should) and not should():
            return
        await self.driver().broadcast(event)

    def channel(self, pattern: str, callback: Callable[..., Any]) -> BroadcastManager:
        """Register a channel-authorization callback for ``pattern`` (e.g. ``chat.{id}``,
        matched against the *bare* channel name — any ``private-``/``presence-`` prefix stripped).
        ``callback(user, *params)`` returns ``bool`` (private) or a ``dict`` of member data
        (presence); a falsy return denies (403 at the ``/broadcasting/auth`` endpoint)."""
        self._channels.append((_compile_channel_pattern(pattern), callback))
        return self

    async def authorize(self, channel_name: str, user: Any) -> bool | dict[str, Any]:
        """Match ``channel_name`` against the registered patterns and run its callback; the first
        match wins. No match, or a falsy callback result, denies (``False``)."""
        bare = channel_name.removeprefix("private-").removeprefix("presence-")
        for compiled, callback in self._channels:
            match = compiled.fullmatch(bare)
            if match is None:
                continue
            outcome = callback(user, *match.groups())
            if inspect.isawaitable(outcome):
                outcome = await outcome
            # a dict (even empty) or True authorizes; only False/None denies. Truthiness would
            # collapse a valid metadata-less presence member ({}) into a denial.
            if outcome is None or outcome is False:
                return False
            return cast("bool | dict[str, Any]", outcome)
        return False


__all__ = [
    "CHANNEL_PREFIX",
    "BroadcastManager",
    "Broadcaster",
    "BroadcastingSettings",
    "Channel",
    "InteractsWithSockets",
    "LogBroadcaster",
    "PresenceChannel",
    "PrivateChannel",
    "RedisBroadcaster",
    "accepts",
    "bind_socket_id",
    "broadcast_payload",
    "channels_for",
    "current_socket_id",
    "event_name",
    "except_socket_id",
]
