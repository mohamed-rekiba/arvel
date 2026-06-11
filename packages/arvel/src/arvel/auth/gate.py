"""Gate — ability-based authorization with before/after hooks.

Fail-closed: unregistered abilities raise AuthorizationException.
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

        # policy lookup: resolve by the first argument's type or any base class
        policy = self._resolve_policy(args[0]) if args else None
        if policy is not None:
            # Policy-level before() runs first: True grants all, False denies all,
            # None falls through to the ability method (Laravel policy filters).
            before = getattr(policy, "before", None)
            if callable(before):
                pre = await self._invoke(before, user, ability)
                if pre is not None:
                    await self._run_after(user, ability, result=bool(pre))
                    return bool(pre)
            method = getattr(policy, ability, None)
            if callable(method):
                result = await self._invoke(method, user, *args)
                await self._run_after(user, ability, result=bool(result))
                return bool(result)
            # The policy owns this model but defines no such ability — deny,
            # matching Laravel (a registered policy is authoritative). Don't fall
            # through to the global ability registry.
            await self._run_after(user, ability, result=False)
            return False

        if ability not in self._abilities:
            # Fail-closed
            raise AuthorizationException(f"Ability '{ability}' is not registered.")

        result = await self._invoke(self._abilities[ability], user, *args)
        await self._run_after(user, ability, result=bool(result))
        return bool(result)

    async def denies(self, ability: str, user: Any, *args: Any) -> bool:
        return not await self.allows(ability, user, *args)

    async def authorize(self, ability: str, user: Any, *args: Any) -> None:
        if not await self.allows(ability, user, *args):
            raise AuthorizationException(f"Not authorized to '{ability}'.")

    def _resolve_policy(self, target: Any) -> Any | None:
        # Walk the MRO so a policy registered on a base class covers subclasses.
        for klass in type(target).__mro__:
            policy = self._policies.get(klass)
            if policy is not None:
                return policy
        return None

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
