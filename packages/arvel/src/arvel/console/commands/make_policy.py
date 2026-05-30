"""``make:policy`` — generate a resource-based authorization policy.

A :class:`arvel.auth.policy.Policy` is generic over the resource type.
Ability methods are named after the action they authorize (``view``,
``update``, ``delete``, …) and **must be async** — the base class
unconditionally awaits them.

Register via ``Gate.policy(MyModel, MyPolicy())`` — pass an **instance**.
"""

from __future__ import annotations

from typing import ClassVar

from arvel.console.commands._base_make import BaseMakeCommand
from arvel.support.str import Str

_TEMPLATE = '''"""{title} — resource authorization policy."""

from __future__ import annotations

from typing import Any

from arvel.auth.policy import Policy


class {title}(Policy[Any]):
    """Authorize actions against a resource.

    Replace ``Any`` with your concrete model class for typed ``resource``
    arguments. Every ability method MUST be ``async`` — the gate awaits
    every call.
    """

    async def view_any(self, user: Any) -> bool:
        """Anyone authenticated can list the resource."""
        return user is not None

    async def view(self, user: Any, resource: Any) -> bool:
        return True

    async def create(self, user: Any) -> bool:
        return user is not None

    async def update(self, user: Any, resource: Any) -> bool:
        return getattr(user, "id", None) == getattr(resource, "owner_id", None)

    async def delete(self, user: Any, resource: Any) -> bool:
        return await self.update(user, resource)
'''


class MakePolicyCommand(BaseMakeCommand):
    name: ClassVar[str] = "make:policy"
    help: ClassVar[str] = "Generate an authorization Policy (async ability methods)"
    _target_subdir: ClassVar[str] = "app/policies"

    def _render(self, name: str) -> str:
        return _TEMPLATE.format(title=Str.pascal(name))
