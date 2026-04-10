"""Rule protocols for the validation layer."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Rule(Protocol):
    """Synchronous validation rule."""

    def passes(self, attribute: str, value: Any, data: dict[str, Any]) -> bool: ...
    def message(self) -> str: ...


@runtime_checkable
class AsyncRule(Protocol):
    """Async validation rule (for DB queries, external calls)."""

    async def passes(self, attribute: str, value: Any, data: dict[str, Any]) -> bool: ...
    def message(self) -> str: ...
