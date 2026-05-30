"""Gate ↔ permissions bridge.

Calling :func:`register_permissions_with_gate` adds a `before` hook to the
``Gate`` that maps every ability check against ``user.has_permission_to(...)``.
That makes the API call sites — ``await gate.allows("posts.edit", user)`` —
work without explicit ``gate.define`` registrations for permission-shaped
abilities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel_permission.service import GuardMismatchError

if TYPE_CHECKING:
    from arvel.auth.gate import Gate


def register_permissions_with_gate(gate: Gate, *, guard: str = "web") -> None:
    """Wire a permission-aware `before` hook onto the given Gate.

    The hook returns True when the user has the ability as a permission, and
    None otherwise — letting policies and explicit ``gate.define`` registrations
    handle abilities that aren't permission-shaped.
    """

    def _hook(user: Any, ability: str) -> bool | None:
        if user is None:
            return None
        has = getattr(user, "has_permission_to", None)
        if not callable(has):
            return None
        try:
            granted = has(ability, guard=guard)
        except GuardMismatchError:
            return None
        return True if granted else None

    gate.before(_hook)
