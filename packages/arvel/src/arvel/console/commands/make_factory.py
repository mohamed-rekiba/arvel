"""``make:factory`` — generate a model factory.

Factories subclass :class:`arvel.database.Factory[T]` and bind a target
model via ``model = SomeModel``. Override :meth:`definition` to return
the dict of attributes used when building each instance.

Usage in tests and seeders::

    instance = await PostFactory().create()           # persisted
    instances = await PostFactory().count(10).create()
    draft = PostFactory().make()                      # in-memory only
"""

from __future__ import annotations

from typing import ClassVar

from arvel.console.commands._base_make import BaseMakeCommand
from arvel.support.str import Str

_TEMPLATE = '''"""{title} — model factory."""

from __future__ import annotations

from typing import Any

from arvel.database import Factory

# Adjust the import path to point at your model module.
# from app.models.{module} import {model}


class {title}(Factory[Any]):
    """Generates fake ``{model}`` instances for tests and seeders."""

    # model = {model}

    def definition(self) -> dict[str, Any]:
        return {{
            # "field": "value",
        }}
'''


class MakeFactoryCommand(BaseMakeCommand):
    name: ClassVar[str] = "make:factory"
    help: ClassVar[str] = "Generate a model factory (arvel.database.Factory)"
    _target_subdir: ClassVar[str] = "database/factories"

    def _render(self, name: str) -> str:
        title = Str.pascal(name)
        model = title.removesuffix("Factory") or title
        return _TEMPLATE.format(title=title, model=model, module=Str.snake(model))
