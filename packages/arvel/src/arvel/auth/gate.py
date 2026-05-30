"""Gate — ability-based authorization with before/after hooks.

Fail-closed: unregistered abilities raise AuthorizationException (ADR-032).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from arvel.auth.exceptions import AuthorizationException


class Gate:
    def __init__(self) -> None:
        self._abilities: dict[str, Callable[..., Any]] = {}
        self._policies: dict[type, Any] = {}
        self._before_callbacks: list[Callable[..., Any]] = []
        self._after_callbacks: list[Callable[..., Any]] = []

    def define(self, ability: str, callback: Callable[..., Any]) -> None:
        self._abilities[ability] = callback

    def policy(self, model_class: type, policy_instance: Any) -> None:
        self._policies[model_class] = policy_instance

    def before(self, callback: Callable[..., Any]) -> None:
        self._before_callbacks.append(callback)

    def after(self, callback: Callable[..., Any]) -> None:
        self._after_callbacks.append(callback)

    async def allows(self, ability: str, user: Any, *args: Any) -> bool:
        # before hooks can short-circuit
        for hook in self._before_callbacks:
            result = hook(user, ability)
            if inspect.isawaitable(result):
                result = await result
            if result is not None:
                return bool(result)

        # policy lookup: if a policy is registered for the first argument's type
        if args and type(args[0]) in self._policies:
            policy = self._policies[type(args[0])]
            if hasattr(policy, ability):
                result = await self._invoke(getattr(policy, ability), user, *args)
                await self._run_after(user, ability, result=bool(result))
                return bool(result)

        if ability not in self._abilities:
            # Fail-closed per ADR-032
            raise AuthorizationException(f"Ability '{ability}' is not registered.")

        result = await self._invoke(self._abilities[ability], user, *args)
        await self._run_after(user, ability, result=bool(result))
        return bool(result)

    async def denies(self, ability: str, user: Any, *args: Any) -> bool:
        return not await self.allows(ability, user, *args)

    async def authorize(self, ability: str, user: Any, *args: Any) -> None:
        if not await self.allows(ability, user, *args):
            raise AuthorizationException(f"Not authorized to '{ability}'.")

    async def _invoke(self, callback: Callable[..., Any], *args: Any) -> Any:
        result = callback(*args)
        if inspect.isawaitable(result):
            return await result
        return result

    async def _run_after(self, user: Any, ability: str, *, result: bool) -> None:
        for hook in self._after_callbacks:
            r = hook(user, ability, result)
            if inspect.isawaitable(r):
                await r
