"""``Context`` facade — static surface over the active context repository."""

from __future__ import annotations

from typing import Any

from arvel.context.repository import DeferredCallback, current_repository


class Context:
    """Read or contribute request-scoped context from anywhere in the call stack.

    Every method delegates to the repository bound for the current request (or a
    lazily-created one in CLI/worker contexts).
    """

    @staticmethod
    def add(key: str, value: Any) -> None:
        current_repository().add(key, value)

    @staticmethod
    def add_hidden(key: str, value: Any) -> None:
        current_repository().add_hidden(key, value)

    @staticmethod
    def push(key: str, *values: Any) -> None:
        current_repository().push(key, *values)

    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        return current_repository().get(key, default)

    @staticmethod
    def get_hidden(key: str, default: Any = None) -> Any:
        return current_repository().get_hidden(key, default)

    @staticmethod
    def has(key: str) -> bool:
        return current_repository().has(key)

    @staticmethod
    def has_hidden(key: str) -> bool:
        return current_repository().has_hidden(key)

    @staticmethod
    def forget(key: str) -> None:
        current_repository().forget(key)

    @staticmethod
    def forget_hidden(key: str) -> None:
        current_repository().forget_hidden(key)

    @staticmethod
    def all() -> dict[str, Any]:
        return current_repository().all()

    @staticmethod
    def all_hidden() -> dict[str, Any]:
        return current_repository().all_hidden()

    @staticmethod
    def keys() -> list[str]:
        return current_repository().keys()

    @staticmethod
    def is_empty() -> bool:
        return current_repository().is_empty()

    @staticmethod
    def flush() -> None:
        current_repository().flush()

    @staticmethod
    def dehydrate() -> dict[str, Any]:
        return current_repository().dehydrate()

    @staticmethod
    def hydrate(data: dict[str, Any]) -> None:
        current_repository().hydrate(data)


def defer(callback: DeferredCallback) -> None:
    """Queue a callback to run after the response is sent (drained by middleware)."""
    current_repository().defer(callback)


__all__ = ["Context", "defer"]
