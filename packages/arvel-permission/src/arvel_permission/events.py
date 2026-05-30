"""Opt-in event system for role/permission mutations.

Enable via ``PermissionConfig(events_enabled=True)``.  Useful for audit logs
and in-process cache invalidation.  Listeners are in-process only — not
integrated with Arvel's async event queue.

Usage::

    from arvel_permission.events import RoleAttachedEvent, on

    @on(RoleAttachedEvent)
    def audit(event: RoleAttachedEvent) -> None:
        logger.info("role attached", model=event.model, role=event.role.name)
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar, overload

if TYPE_CHECKING:
    from arvel_permission.models import Permission, Role

_E = TypeVar("_E")

_listeners: defaultdict[type[Any], list[Callable[..., None]]] = defaultdict(list)


@overload
def on(
    event_type: type[_E],
    handler: None = ...,
) -> Callable[[Callable[[_E], None]], Callable[[_E], None]]: ...


@overload
def on(
    event_type: type[_E],
    handler: Callable[[_E], None],
) -> None: ...


def on(
    event_type: type[_E],
    handler: Callable[[_E], None] | None = None,
) -> Callable[[Callable[[_E], None]], Callable[[_E], None]] | None:
    """Register a listener for *event_type*.

    Can be used as a decorator::

        @on(RoleAttachedEvent)
        def my_handler(evt): ...

    Or called directly::

        on(RoleAttachedEvent, my_handler)
    """
    if handler is not None:
        _listeners[event_type].append(handler)
        return None

    def _decorator(fn: Callable[[_E], None]) -> Callable[[_E], None]:
        _listeners[event_type].append(fn)
        return fn

    return _decorator


def fire(event: object) -> None:
    """Dispatch *event* to all registered listeners for its type."""
    for handler in _listeners.get(type(event), []):
        handler(event)


def clear_listeners() -> None:
    """Drop all registered listeners. Primarily for test isolation."""
    _listeners.clear()


@dataclass(frozen=True)
class RoleAttachedEvent:
    """Fired after a role is attached to a model."""

    model: object
    role: Role | None


@dataclass(frozen=True)
class RoleDetachedEvent:
    """Fired after a role is detached from a model."""

    model: object
    role: Role | None


@dataclass(frozen=True)
class PermissionAttachedEvent:
    """Fired after a permission is granted directly to a model."""

    model: object
    permission: Permission | None


@dataclass(frozen=True)
class PermissionDetachedEvent:
    """Fired after a direct permission grant is revoked from a model."""

    model: object
    permission: Permission | None
