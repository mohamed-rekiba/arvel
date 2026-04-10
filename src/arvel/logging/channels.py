"""Channel registry and configuration for public logger facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from arvel.logging.errors import InvalidLogChannelConfigurationError, UnknownLogChannelError

LogDriver = Literal["stderr", "single", "daily"]


@dataclass(frozen=True, slots=True)
class ChannelDefinition:
    """Concrete configuration for a named log channel."""

    name: str
    driver: LogDriver


@dataclass(slots=True)
class ChannelRegistry:
    """In-memory registry of known channels and default selection."""

    channels: dict[str, ChannelDefinition]
    default_channel: str

    @classmethod
    def default(cls) -> ChannelRegistry:
        """Return built-in channels and default policy."""
        builtins = {
            "stderr": ChannelDefinition(name="stderr", driver="stderr"),
            "single": ChannelDefinition(name="single", driver="single"),
            "daily": ChannelDefinition(name="daily", driver="daily"),
        }
        return cls(channels=builtins, default_channel="stderr")

    def resolve(self, name: str | None = None) -> ChannelDefinition:
        """Resolve explicit or default channel definition."""
        selected_name = name if name is not None else self.default_channel
        selected = self.channels.get(selected_name)
        if selected is None:
            available = ", ".join(sorted(self.channels))
            raise UnknownLogChannelError(
                f"Unknown log channel '{selected_name}'. Available channels: {available}",
            )
        return selected


_registry: ChannelRegistry = ChannelRegistry.default()


def configure_channels(
    *,
    default_channel: str,
    channels: dict[str, LogDriver],
) -> None:
    """Configure known channels used by the public logger facade."""
    if not channels:
        raise InvalidLogChannelConfigurationError("channels cannot be empty")
    if default_channel not in channels:
        raise InvalidLogChannelConfigurationError(
            f"default_channel '{default_channel}' is not present in channels",
        )
    configured = {
        name: ChannelDefinition(name=name, driver=driver) for name, driver in channels.items()
    }
    global _registry
    _registry = ChannelRegistry(channels=configured, default_channel=default_channel)


def reset_channels() -> None:
    """Reset to built-in channel defaults."""
    global _registry
    _registry = ChannelRegistry.default()


def resolve_channel(name: str | None = None) -> ChannelDefinition:
    """Resolve a channel using the current global registry."""
    return _registry.resolve(name)
