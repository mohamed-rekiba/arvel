"""ChannelAuthorizer — callback-based channel authorization."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from arvel.broadcasting.channels import Channel, PresenceChannel, PrivateChannel
from arvel.logging import Log

if TYPE_CHECKING:
    from arvel.auth.policy import AuthContext

logger = Log.named("arvel.broadcasting.authorizer")

PrivateCallback = Callable[..., bool]
PresenceCallback = Callable[..., dict[str, Any] | None]


class _ChannelRegistration:
    __slots__ = ("callback", "channel_type", "param_names", "pattern", "regex")

    def __init__(
        self,
        pattern: str,
        callback: PrivateCallback | PresenceCallback,
        channel_type: type[Channel],
    ) -> None:
        self.pattern = pattern
        self.callback = callback
        self.channel_type = channel_type

        self.param_names: list[str] = re.findall(r"\{(\w+)\}", pattern)
        regex_pattern = re.escape(pattern)
        for name in self.param_names:
            regex_pattern = regex_pattern.replace(re.escape(f"{{{name}}}"), r"([^.]+)")
        self.regex = re.compile(f"^{regex_pattern}$")


class ChannelAuthorizer:
    """Registry of channel authorization callbacks.

    Supports public (no auth), private (bool callback), and
    presence (dict callback) channels.
    """

    def __init__(self) -> None:
        self._registrations: list[_ChannelRegistration] = []

    def private(self, pattern: str, callback: PrivateCallback) -> None:
        """Register an authorization callback for a private channel pattern."""
        self._registrations.append(_ChannelRegistration(pattern, callback, PrivateChannel))

    def presence(self, pattern: str, callback: PresenceCallback) -> None:
        """Register an authorization callback for a presence channel pattern."""
        self._registrations.append(_ChannelRegistration(pattern, callback, PresenceChannel))

    async def authorize(
        self,
        auth_context: AuthContext,
        channel: Channel,
    ) -> bool | dict[str, Any] | None:
        """Check whether *auth_context* is authorized for *channel*.

        Returns True for public channels. For private channels, returns the
        callback result (bool). For presence channels, returns user metadata
        dict or None.
        """
        if type(channel) is Channel:
            return True

        for reg in self._registrations:
            match = reg.regex.match(channel.name)
            if match:
                params = dict(zip(reg.param_names, match.groups(), strict=False))
                result = reg.callback(auth_context, **params)
                logger.debug(
                    "channel_auth",
                    channel=channel.name,
                    pattern=reg.pattern,
                    result=result,
                )
                return result

        logger.info("channel_auth_denied", channel=channel.name, reason="no_matching_pattern")
        if isinstance(channel, PresenceChannel):
            return None
        return False
