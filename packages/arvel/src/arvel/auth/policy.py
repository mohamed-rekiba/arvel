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
        # before() short-circuits: True grants all, False denies all, None falls through.
        before = getattr(self, "before", None)
        if callable(before):
            pre = before(user, ability)
            if inspect.isawaitable(pre):
                pre = await pre
            if pre is not None:
                return bool(pre)
        method = getattr(self, ability, None)
        if method is None:
            return False
        result = method(user, resource) if resource is not None else method(user)
        if inspect.isawaitable(result):
            return bool(await result)
        return bool(result)
