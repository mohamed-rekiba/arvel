"""ChannelRegistry + channel-name validation (FR-013-011, FR-013-012, SEC-013-004/008, ADR-054)."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from arvel.broadcasting.exceptions import BroadcastChannelError
from arvel.logging.facade import Log

logger = Log.channel(__name__)


# Allowed channel-name characters per Pusher spec: alphanumerics, "-", "_", ".",
# "=", "@", ",", ";".
_CHANNEL_NAME_RE = re.compile(r"^[A-Za-z0-9_\-.=@,;]{1,1024}$")

# Placeholder format inside a pattern, e.g. {id}.
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

# Each {placeholder} is replaced with this regex segment (no '.' or '/').
_PLACEHOLDER_SEGMENT = r"([^./]+)"


def validate_channel_name(name: str) -> None:
    """Reject malformed channel names (SEC-013-004 / SEC-013-008)."""
    if not _CHANNEL_NAME_RE.fullmatch(name):
        raise BroadcastChannelError(f"Invalid channel name: {name!r}")


def compile_pattern(pattern: str) -> re.Pattern[str]:
    """Turn ``private-user.{id}`` into a fully anchored regex (ADR-054).

    Literal segments are ``re.escape``d to avoid regex-meta interpretation;
    placeholders become named capture groups so callers can pull them back as kwargs.
    """
    parts: list[str] = []
    last: int = 0
    seen: dict[str, int] = {}
    for match in _PLACEHOLDER_RE.finditer(pattern):
        parts.append(re.escape(pattern[last : match.start()]))
        name = match.group(1)
        # If a placeholder repeats, use a non-capturing reference to the prior group.
        if name in seen:
            parts.append(f"(?P={name})")
        else:
            parts.append(f"(?P<{name}>{_PLACEHOLDER_SEGMENT[1:-1]})")
            seen[name] = match.start()
        last = match.end()
    parts.append(re.escape(pattern[last:]))
    return re.compile(f"^{''.join(parts)}$")


@dataclass
class _Entry:
    pattern: str
    compiled: re.Pattern[str]
    callback: Callable[..., Awaitable[Any]]


@dataclass
class ChannelRegistry:
    """Holds the channel pattern → authorization callback mapping (FR-013-011).

    Patterns are matched in registration order. First match wins.
    """

    _entries: list[_Entry] = field(default_factory=list[_Entry])

    def register(
        self,
        pattern: str,
        callback: Callable[..., Awaitable[Any]],
    ) -> ChannelRegistry:
        self._entries.append(
            _Entry(pattern=pattern, compiled=compile_pattern(pattern), callback=callback),
        )
        return self

    def unregister(self, pattern: str) -> None:
        self._entries = [e for e in self._entries if e.pattern != pattern]

    def match(self, channel: str) -> tuple[_Entry, dict[str, str]] | None:
        for entry in self._entries:
            m = entry.compiled.fullmatch(channel)
            if m is not None:
                return entry, m.groupdict()
        return None

    async def authorize(self, channel: str, *, user: object) -> Any:
        """Run the matching callback and return its result.

        ``False`` / ``None`` → rejection. A dict for presence channels.
        Raised exceptions are caught and logged; the function then returns ``False``.
        """
        hit = self.match(channel)
        if hit is None:
            return False
        entry, kwargs = hit
        try:
            result = await entry.callback(user, **kwargs)
        except Exception as exc:  # noqa: BLE001 — callbacks may raise anything
            logger.warning(
                "broadcast_channel_callback_error",
                channel=channel,
                pattern=entry.pattern,
                error=type(exc).__name__,
            )
            return False
        return result or False


__all__ = ["ChannelRegistry", "compile_pattern", "validate_channel_name"]
