"""Policy[T] — resource-based authorization ABC."""

from __future__ import annotations

import inspect
from abc import ABC
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class Policy(ABC, Generic[T]):
    """Base class for resource-based authorization policies.

    Subclass and implement methods named after abilities (view, update, delete, etc.).
    Each method receives (user, resource) and returns bool.
    """

    async def check(self, ability: str, user: Any, resource: T | None = None) -> bool:
        method = getattr(self, ability, None)
        if method is None:
            return False
        result = method(user, resource) if resource is not None else method(user)
        if inspect.isawaitable(result):
            return bool(await result)
        return bool(result)
