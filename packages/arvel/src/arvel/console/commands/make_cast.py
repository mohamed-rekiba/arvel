"""``make:cast`` — generate a custom column-type cast.

The generated file is a ``sqlalchemy.types.TypeDecorator`` subclass — the
canonical way to add a custom column type in Arvel. The stub round-trips
JSON by default; the developer typically only needs to swap the
``impl`` and the two ``process_*`` bodies.

For trivial per-attribute coercion, prefer the model-level ``__casts__``
shortcut (``{"is_active": "boolean"}``) over a custom ``TypeDecorator``.
"""

from __future__ import annotations

from typing import ClassVar

from arvel.console.commands._base_make import BaseMakeCommand
from arvel.support.str import Str

_TEMPLATE = '''"""{title} — custom column cast."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import String
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class {title}(TypeDecorator[dict[str, Any]]):
    """Persist a Python ``dict`` as a JSON string column."""

    impl = String
    cache_ok = True

    def process_bind_param(
        self,
        value: dict[str, Any] | None,
        dialect: Dialect,
    ) -> str | None:
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(
        self,
        value: Any,
        dialect: Dialect,
    ) -> dict[str, Any] | None:
        if value is None:
            return None
        return json.loads(value)
'''


class MakeCastCommand(BaseMakeCommand):
    name: ClassVar[str] = "make:cast"
    help: ClassVar[str] = "Generate a custom column cast (SQLAlchemy TypeDecorator)"
    _target_subdir: ClassVar[str] = "app/casts"

    def _render(self, name: str) -> str:
        return _TEMPLATE.format(title=Str.pascal(name))
