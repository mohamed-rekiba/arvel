"""Policy-based authorization — deny by default, method-per-action pattern.

Supports both simple user-based policies and OIDC claims-aware policies
that check roles and groups extracted from JWT/OIDC tokens.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from arvel.logging import Log
from arvel.security.exceptions import AuthorizationError

logger = Log.named("arvel.auth.policy")

BeforeHook = Callable[["AuthContext | object", str], Awaitable[bool | None]]
AfterHook = Callable[["AuthContext | object", str, bool], Awaitable[bool | None]]


@dataclass
class AuthContext:
    """Authentication context passed to policies.

    Wraps the user object along with roles and groups extracted from
    JWT/OIDC claims. Policies can check ``ctx.has_role("admin")`` or
    ``ctx.in_group("/org/editors")`` directly.
    """

    user: object
    sub: str = ""
    roles: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    claims: dict[str, Any] = field(default_factory=dict)
    guard: str = ""

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def has_any_role(self, *roles: str) -> bool:
        return bool(set(roles) & set(self.roles))

    def in_group(self, group: str) -> bool:
        return group in self.groups

    def in_any_group(self, *groups: str) -> bool:
        return bool(set(groups) & set(self.groups))


class Policy:
    """Base class for authorization policies.

    Subclass and implement action methods (``view``, ``create``, ``update``,
    ``delete``) returning bool. Override ``before()`` for super-admin bypass.

    The ``user`` parameter can be a plain user object or an ``AuthContext``
    wrapping user + roles + groups.
    """

    async def before(self, user: AuthContext | object, action: str) -> bool | None:
        """Pre-check hook. Return True/False to short-circuit, None to continue."""
        return None

    async def view_any(self, user: AuthContext | object) -> bool:
        return False

    async def view(self, user: AuthContext | object, resource: object) -> bool:
        return False

    async def create(self, user: AuthContext | object) -> bool:
        return False

    async def update(self, user: AuthContext | object, resource: object) -> bool:
        return False

    async def delete(self, user: AuthContext | object, resource: object) -> bool:
        return False


class RoleBasedPolicy(Policy):
    """Policy that checks roles from OIDC claims.

    Define ``allowed_roles`` per action. If the user (via ``AuthContext``)
    has any of the allowed roles, access is granted.
    """

    role_action_map: dict[str, list[str]] = {}  # noqa: RUF012
    admin_roles: list[str] = ["admin", "super-admin"]  # noqa: RUF012

    async def before(self, user: AuthContext | object, action: str) -> bool | None:
        if isinstance(user, AuthContext) and user.has_any_role(*self.admin_roles):
            return True
        return None

    async def _check_role(self, user: AuthContext | object, action: str) -> bool:
        if not isinstance(user, AuthContext):
            return False
        allowed = self.role_action_map.get(action, [])
        if not allowed:
            return False
        return user.has_any_role(*allowed)

    async def view_any(self, user: AuthContext | object) -> bool:
        return await self._check_role(user, "view_any")

    async def view(self, user: AuthContext | object, resource: object) -> bool:
        return await self._check_role(user, "view")

    async def create(self, user: AuthContext | object) -> bool:
        return await self._check_role(user, "create")

    async def update(self, user: AuthContext | object, resource: object) -> bool:
        return await self._check_role(user, "update")

    async def delete(self, user: AuthContext | object, resource: object) -> bool:
        return await self._check_role(user, "delete")


class PolicyRegistry:
    """Maps model types to their policy classes. Deny-by-default when no policy registered."""

    def __init__(self) -> None:
        self._policies: dict[type, type[Policy]] = {}

    def register(self, model_type: type, policy_type: type[Policy]) -> None:
        self._policies[model_type] = policy_type

    def get(self, model_type: type) -> type[Policy] | None:
        return self._policies.get(model_type)

    def has(self, model_type: type) -> bool:
        return model_type in self._policies


class Gate:
    """Authorization gate — checks policies for user actions on resources.

    Supports global ``before()`` and ``after()`` hooks that run around
    policy evaluation. Before hooks can short-circuit; after hooks can
    override the policy result.
    """

    def __init__(self, registry: PolicyRegistry) -> None:
        self._registry = registry
        self._before_hooks: list[BeforeHook] = []
        self._after_hooks: list[AfterHook] = []

    def before(self, hook: BeforeHook) -> None:
        """Register a global before-authorization hook.

        The hook receives ``(user, ability)`` and returns:
        - ``True`` to grant immediately (short-circuit)
        - ``False`` to deny immediately (short-circuit)
        - ``None`` to continue to the next hook or policy
        """
        self._before_hooks.append(hook)

    def after(self, hook: AfterHook) -> None:
        """Register a global after-authorization hook.

        The hook receives ``(user, ability, result)`` and returns:
        - ``True``/``False`` to override the policy result
        - ``None`` to keep the current result
        """
        self._after_hooks.append(hook)

    async def _run_before_hooks(self, user: AuthContext | object, action: str) -> bool | None:
        for hook in self._before_hooks:
            result = await hook(user, action)
            if result is not None:
                return bool(result)
        return None

    async def _run_after_hooks(self, user: AuthContext | object, action: str, result: bool) -> bool:
        current = result
        for hook in self._after_hooks:
            override = await hook(user, action, current)
            if override is not None:
                current = bool(override)
        return current

    async def allows(
        self,
        user: AuthContext | object,
        action: str,
        resource: object | None = None,
        *,
        resource_type: type | None = None,
    ) -> bool:
        """Check if user is allowed to perform action. Returns bool."""
        before_result = await self._run_before_hooks(user, action)
        if before_result is not None:
            return before_result

        model_type = resource_type or (type(resource) if resource is not None else None)
        if model_type is None:
            logger.warning("Gate.allows called without resource or resource_type — denied")
            return False

        policy_cls = self._registry.get(model_type)
        if policy_cls is None:
            logger.info(
                "No policy registered for %s — denied by default",
                model_type.__name__,
            )
            return False

        policy = policy_cls()

        policy_before = await policy.before(user, action)
        if policy_before is True:
            logger.info(
                "Policy %s.before() granted %s on %s",
                policy_cls.__name__,
                action,
                model_type.__name__,
            )
            result = True
            return await self._run_after_hooks(user, action, result)
        if policy_before is False:
            return await self._run_after_hooks(user, action, False)

        method = getattr(policy, action, None)
        if method is None:
            logger.warning(
                "Policy %s has no method '%s' — denied",
                policy_cls.__name__,
                action,
            )
            return await self._run_after_hooks(user, action, False)

        if resource is not None:
            result = await method(user, resource)
        else:
            result = await method(user)

        policy_result = bool(result)
        logger.info(
            "Policy %s.%s() → %s for user %s on %s",
            policy_cls.__name__,
            action,
            policy_result,
            user,
            model_type.__name__,
        )
        return await self._run_after_hooks(user, action, policy_result)

    async def authorize(
        self,
        user: AuthContext | object,
        action: str,
        resource: object | None = None,
        *,
        resource_type: type | None = None,
    ) -> None:
        """Check authorization and raise AuthorizationError if denied."""
        allowed = await self.allows(user, action, resource, resource_type=resource_type)
        if not allowed:
            model_name = ""
            if resource_type:
                model_name = resource_type.__name__
            elif resource is not None:
                model_name = type(resource).__name__
            raise AuthorizationError(
                f"Not authorized to {action} {model_name}",
                action=action,
                resource=model_name,
            )
