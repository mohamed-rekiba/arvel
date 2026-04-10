"""AuthManager — central registry for named authentication guards."""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arvel.auth.contracts import GuardContract


class AuthManager:
    """Manages named authentication guards with a configurable default.

    Guards are registered at boot time and frozen. At request time, the
    middleware asks the manager for a guard by name (or the default).
    """

    def __init__(
        self,
        *,
        guards: dict[str, GuardContract],
        default: str,
    ) -> None:
        if not guards:
            msg = "At least one guard must be registered"
            raise ValueError(msg)

        if default not in guards:
            msg = f"default guard '{default}' is not registered"
            raise ValueError(msg)

        self._guards: MappingProxyType[str, GuardContract] = MappingProxyType(guards)
        self._default = default

    def guard(self, name: str | None = None) -> GuardContract:
        """Resolve a guard by name, falling back to the default."""
        resolved = name if name is not None else self._default

        if resolved not in self._guards:
            msg = f"unknown guard '{resolved}'"
            raise ValueError(msg)

        return self._guards[resolved]

    @property
    def default_name(self) -> str:
        return self._default
