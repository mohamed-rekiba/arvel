"""arvel.auth.gate — authorization Gate + Policy resolution (Laravel ``Gate``).

Abilities are defined inline (``Gate.define``) or resolved to a Policy class method
(``Gate.policy(Post, PostPolicy)``); ``before`` hooks short-circuit (super-admins).
Pure-Python, no engine. Grounded in knowledge/port/15-auth-authorization.md.
"""

from __future__ import annotations

import inspect
from typing import Any


class AuthorizationError(Exception):
    """Raised by ``Gate.authorize`` when an ability is denied.

    Carries the **status** (``.status``, default 403 — e.g. 404 for ``deny_as_not_found``) and the
    **message** (``.detail``) from the policy's :class:`GateResponse`. The HTTP kernel's exception
    renderer reads ``.status``/``.detail`` (see ``render_exception``), so a denial renders as the
    right status + custom message instead of a generic 500 — Laravel ``AuthorizationException``."""

    def __init__(self, ability: str, message: str | None = None, code: int = 403) -> None:
        self.ability = ability
        msg = message or f"This action is unauthorized: {ability}"
        self.status = code  # → HTTP status via render_exception (403 default, 404 for not-found)
        self.detail = msg  # → response message via render_exception (the custom deny message)
        super().__init__(msg)


class GateResponse:
    """An allow/deny result carrying an optional message + code (``Gate.inspect``)."""

    def __init__(self, allowed: bool, message: str | None = None, code: int | None = None) -> None:
        self.allowed = allowed
        self.message = message
        self.code = code

    def __bool__(self) -> bool:
        return self.allowed

    @classmethod
    def allow(cls) -> GateResponse:
        return cls(True)

    @classmethod
    def deny(cls, message: str = "This action is unauthorized.", code: int = 403) -> GateResponse:
        return cls(False, message, code)

    @classmethod
    def deny_as_not_found(cls, message: str = "Not Found", code: int = 404) -> GateResponse:
        """Deny but render as **404** — hide a resource's existence (Laravel ``denyAsNotFound``)."""
        return cls(False, message, code)


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


class Gate:
    """Ability registry + policy resolution against the current (or given) user."""

    def __init__(self) -> None:
        self._abilities: dict[str, Any] = {}
        self._policies: dict[type, Any] = {}
        self._before: list[Any] = []
        self._after: list[Any] = []

    def define(self, ability: str, callback: Any) -> Gate:
        self._abilities[ability] = callback
        return self

    def has_ability(self, ability: str) -> bool:
        """Whether ``ability`` is registered via :meth:`define` (a named ability).

        Note: abilities served only by a registered policy method or a ``before`` hook are not named
        here — this reports the ``define``-registered set, which is what ``Authorize(ability)`` and the
        boot-time ability assertion check against.
        """
        return ability in self._abilities

    def policy(self, model: type, policy: Any) -> Gate:
        self._policies[model] = policy
        return self

    def before(self, callback: Any) -> Gate:
        """Register a hook run *before* the check — a non-``None`` return short-circuits it
        (e.g. a super-admin who passes every ability). Signature: ``(user, ability)``."""
        self._before.append(callback)
        return self

    def after(self, callback: Any) -> Gate:
        """Register a hook run *after* the check — a non-``None`` return overrides the result
        (e.g. a global deny during read-only mode). Runs even when a ``before`` hook
        short-circuited. Signature: ``(user, ability, result, args)``."""
        self._after.append(callback)
        return self

    def _current_user(self) -> Any:
        from arvel.auth import current_user

        return current_user.get()

    def _policy_instance(self, args: tuple[Any, ...]) -> Any:
        """The registered policy instance for ``args[0]``'s model, or ``None``."""
        if not args:
            return None
        target = args[0]
        model = target if isinstance(target, type) else type(target)
        policy = self._policies.get(model)
        if policy is None:
            return None
        return policy() if isinstance(policy, type) else policy

    def _resolve(self, ability: str, args: tuple[Any, ...]) -> Any:
        if ability in self._abilities:
            return self._abilities[ability]
        instance = self._policy_instance(args)
        if instance is not None:
            method = getattr(instance, ability, None)
            if callable(method):
                return method
        return None

    async def _raw(self, ability: str, args: tuple[Any, ...], user: Any) -> Any:
        """The raw allow/deny result: Gate ``before`` hooks (short-circuit) → the policy's own
        ``before`` (super-admin auto-grant) → the ability/policy-method check → ``after`` hooks
        (override). ``after`` runs in every case, even after a short-circuit."""
        result: Any = None
        for hook in self._before:
            result = await _maybe_await(hook(user, ability))
            if result is not None:
                break
        if result is None:
            # a policy's own before() runs before its ability methods (Laravel parity)
            if ability not in self._abilities:
                instance = self._policy_instance(args)
                pre = getattr(instance, "before", None) if instance is not None else None
                if callable(pre):
                    result = await _maybe_await(pre(user, ability))
            if result is None:
                check = self._resolve(ability, args)
                result = None if check is None else await _maybe_await(check(user, *args))
        for hook in self._after:
            override = await _maybe_await(hook(user, ability, result, args))
            if override is not None:
                result = override
        return result

    async def allows(self, ability: str, *args: Any, user: Any = None) -> bool:
        user = user if user is not None else self._current_user()
        return bool(await self._raw(ability, args, user))

    async def denies(self, ability: str, *args: Any, user: Any = None) -> bool:
        return not await self.allows(ability, *args, user=user)

    async def authorize(self, ability: str, *args: Any, user: Any = None) -> None:
        """Raise :class:`AuthorizationError` (carrying the policy's deny message + status) when denied."""
        response = await self.inspect(ability, *args, user=user)
        if not response.allowed:
            raise AuthorizationError(
                ability, response.message, response.code if response.code is not None else 403
            )

    async def inspect(self, ability: str, *args: Any, user: Any = None) -> GateResponse:
        """The full :class:`GateResponse` — preserving a policy's custom deny message + code (so
        ``deny("…", 404)`` / ``deny_as_not_found()`` survive to the caller), not a generic deny."""
        user = user if user is not None else self._current_user()
        result = await self._raw(ability, args, user)
        if isinstance(result, GateResponse):
            return result
        return GateResponse.allow() if bool(result) else GateResponse.deny()

    async def any(self, abilities: list[str], *args: Any, user: Any = None) -> bool:
        for ability in abilities:
            if await self.allows(ability, *args, user=user):
                return True
        return False

    async def none(self, abilities: list[str], *args: Any, user: Any = None) -> bool:
        return not await self.any(abilities, *args, user=user)
