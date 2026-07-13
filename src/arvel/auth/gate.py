"""arvel.auth.gate — authorization Gate + Policy resolution.

Abilities are defined inline (``Gate.define``) or resolved to a Policy class method
(``Gate.policy(Post, PostPolicy)``); ``before`` hooks short-circuit (super-admins).
Pure-Python, no engine. Grounded in knowledge/port/15-auth-authorization.md.

Policy resolution (:meth:`Gate.resolve_policy`) has three tiers, checked in order: an explicit
``Gate.policy(Model, Policy)`` registration wins; else a ``__policy__`` classvar on the model itself
(typed, preferred — ``class Post(Model): __policy__ = PostPolicy``); else a provider-registered
convention map (:meth:`Gate.register_policies`). "Auto-discovery" here means that last, provider-built
map — an app's ``AuthServiceProvider`` scans its own ``policies/`` package and hands the resulting
``{Model: Policy}`` dict to ``register_policies``. There is no filesystem/import magic on arvel's
side (Python has no PSR-4 class-name guess like 's); the scan is the app's to write.

Gate guest handling: before invoking an ability/policy callback with ``user=None`` (no authenticated
user), :func:`_accepts_none` inspects the callback's first parameter type annotation. A non-nullable
annotation (``User``, not ``User | None``/``Optional[User]``) auto-denies the guest instead of risking
an ``AttributeError`` inside a callback written assuming a real user; a nullable annotation means the
callback opted into guest evaluation, so it's invoked with ``None``. An *unannotated* first parameter
(most lambdas) or one explicitly typed ``Any`` is treated as nullable — permissive, unchanged
behavior for untyped callbacks. The check result is cached per callback (``id`` of the underlying
function).
"""

from __future__ import annotations

import inspect
import types
import typing
from typing import Any


class AuthorizationError(Exception):
    """Raised by ``Gate.authorize`` when an ability is denied.

    Carries the **status** (``.status``, default 403 — e.g. 404 for ``deny_as_not_found``) and the
    **message** (``.detail``) from the policy's :class:`GateResponse`. The HTTP kernel's exception
    renderer reads ``.status``/``.detail`` (see ``render_exception``), so a denial renders as the
    right status + custom message instead of a generic 500 — ``AuthorizationException``."""

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
        """Deny but render as **404** — hide a resource's existence."""
        return cls(False, message, code)


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


_UNRESOLVED: Any = object()


def _split_top_level(text: str, sep: str) -> list[str]:
    """Split ``text`` on ``sep`` only at bracket depth 0, so a separator nested inside ``[...]``
    (e.g. the comma in ``dict[str, int]``) is not a split point."""
    parts: list[str] = []
    depth = 0
    current = ""
    for ch in text:
        if ch in "[(":
            depth += 1
        elif ch in "])":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)
    return parts


def _annotation_str_is_nullable(raw: Any) -> bool:
    """Nullability check on an *unresolved* annotation (a string under ``from __future__ import
    annotations``, or a live object). Nullable only when the annotation **structurally** admits
    ``None`` — ``None``/``NoneType``, ``Optional[X]``, a top-level ``X | None`` union, or a
    ``Union[..., None, ...]`` with ``None`` as a top-level arg. A *nested* ``None`` (``dict[str,
    None]``) is NOT nullable — the check is bracket-depth-aware, not a substring match. Anything
    else fails closed."""
    text = raw if isinstance(raw, str) else getattr(raw, "__name__", str(raw))
    s = text.replace(" ", "")
    if s in ("None", "NoneType"):
        return True
    if s.startswith("Optional["):
        return True
    if any(part in ("None", "NoneType") for part in _split_top_level(s, "|")):
        return True  # top-level "X | None"
    if s.startswith("Union[") and s.endswith("]"):
        args = _split_top_level(s[len("Union[") : -1], ",")
        if any(arg in ("None", "NoneType") for arg in args):
            return True
    return False


def _accepts_none(callback: Any) -> bool:
    """Whether ``callback``'s first parameter's type hint admits ``None`` (``X | None`` /
    ``Optional[X]``). An *unannotated* first parameter counts as nullable (permissive default —
    the plain-lambda case). A parameter annotated with a **non-nullable** type auto-denies the
    guest — and this holds even when the annotation can't be resolved to a runtime object: under
    ``from __future__ import annotations`` a ``TYPE_CHECKING``-only model import leaves the hint an
    unresolvable string, and a security predicate must NOT fall open there. So on a
    ``get_type_hints`` failure we fall back to the raw signature annotation and treat any present,
    non-``Optional`` annotation as non-nullable (auto-deny). Only a genuinely absent annotation
    stays permissive."""
    try:
        signature = inspect.signature(callback)
    except TypeError, ValueError:
        return True
    params = list(signature.parameters.values())
    if not params:
        return True
    first = params[0]
    try:
        hints = typing.get_type_hints(callback)
        hint: Any = hints.get(first.name, _UNRESOLVED)
    except Exception:
        hint = _UNRESOLVED
    if hint is _UNRESOLVED:
        raw = first.annotation
        if raw is inspect.Parameter.empty:
            return True  # no annotation at all → permissive (unchanged lambda behavior)
        return _annotation_str_is_nullable(
            raw
        )  # present but unresolved → fail closed unless ?|None
    if hint is None or hint is Any:
        return True  # unannotated, or explicitly untyped (Any accepts None too)
    origin = typing.get_origin(hint)
    if origin is typing.Union or origin is types.UnionType:
        return type(None) in typing.get_args(hint)
    return hint is type(None)


class Gate:
    """Ability registry + policy resolution against the current (or given) user."""

    def __init__(self) -> None:
        self._abilities: dict[str, Any] = {}
        self._policies: dict[type, Any] = {}
        self._policy_registry: dict[type, Any] = {}
        self._before: list[Any] = []
        self._after: list[Any] = []
        self._nullable_cache: dict[int, bool] = {}

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

    def register_policies(self, policies: dict[type, Any]) -> Gate:
        """Bulk-register a provider-built convention map (``{Model: Policy}``) — the lowest-priority
        tier of :meth:`resolve_policy`. This is arvel's "auto-discovery": an app provider scans its
        own ``policies/`` package and hands the result here; there is no import/filesystem magic on
        arvel's side."""
        self._policy_registry.update(policies)
        return self

    def resolve_policy(self, model: type) -> Any:
        """The policy instance for ``model``, or ``None`` if none applies. Checked in order: an
        explicit :meth:`policy` registration (wins) → the model's own ``__policy__`` classvar (typed,
        preferred) → the provider-registered convention map (:meth:`register_policies`)."""
        policy = self._policies.get(model)
        if policy is None:
            policy = getattr(model, "__policy__", None)
        if policy is None:
            policy = self._policy_registry.get(model)
        if policy is None:
            return None
        return policy() if isinstance(policy, type) else policy

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
        """The resolved policy instance for ``args[0]``'s model, or ``None`` (see :meth:`resolve_policy`)."""
        if not args:
            return None
        target = args[0]
        model = target if isinstance(target, type) else type(target)
        return self.resolve_policy(model)

    def _nullable(self, callback: Any) -> bool:
        """Cached :func:`_accepts_none` — keyed by the underlying function's ``id`` (a bound
        method's ``self`` need not be hashable), since callbacks are stable for a Gate's lifetime."""
        key = id(getattr(callback, "__func__", callback))
        cached = self._nullable_cache.get(key)
        if cached is None:
            cached = self._nullable_cache[key] = _accepts_none(callback)
        return cached

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
            # ONE policy instance decides the whole check. Its before() runs whenever a policy
            # is registered for the model — the documented model-wide super-admin grant — even
            # when the policy lacks this ability's method, and a same-named `define` must not
            # suppress it.
            instance = self._policy_instance(args)
            pre = getattr(instance, "before", None) if instance is not None else None
            if callable(pre):
                result = await _maybe_await(pre(user, ability))
            if result is None:
                # documented order: the policy method decides for its model; a same-named
                # `define` is only the fallthrough (no policy, or the policy lacks the method).
                # NB: ANY public callable on the policy matching the ability name is treated as
                # the ability method — keep policy helpers private (_-prefixed)
                method = getattr(instance, ability, None) if instance is not None else None
                check = method if callable(method) else self._abilities.get(ability)
                if check is None:
                    result = None
                elif user is None and not self._nullable(check):
                    # a guest + a callback typed for a real user → auto-deny, never call with None
                    result = GateResponse.deny()
                else:
                    result = await _maybe_await(check(user, *args))
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


__all__ = ["AuthorizationError", "Gate", "GateResponse"]
