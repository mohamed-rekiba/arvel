"""``make:resource`` — generate a JSON resource transformer.

JSON resources turn domain objects (typically ORM models) into JSON-ready
dicts for responses. Subclass :class:`arvel.http.JsonResource[T]`,
parameterize ``T`` with your model, and implement
``to_dict(self, request) -> dict[str, Any]``.

Use the class on a single instance with ``MyResource(instance).to_dict(request)``
or on a list with ``MyResource.collection(items).to_dict(request)``.
"""

from __future__ import annotations

from typing import ClassVar

from arvel.console.commands._base_make import BaseMakeCommand
from arvel.support.str import Str

_TEMPLATE = '''"""{title} — JSON resource transformer."""

from __future__ import annotations

from typing import Any

from arvel.http import JsonResource


class {title}(JsonResource[Any]):
    """Transforms a single ``{model}`` into a JSON dict."""

    def to_dict(self, request: Any) -> dict[str, Any]:
        return {{
            # "id": self.resource.id,
            # "name": self.resource.name,
        }}
'''


class MakeResourceCommand(BaseMakeCommand):
    name: ClassVar[str] = "make:resource"
    help: ClassVar[str] = "Generate a JsonResource transformer (arvel.http.JsonResource)"
    _target_subdir: ClassVar[str] = "app/http/resources"
    _suffix: ClassVar[str] = "Resource"

    def _render(self, name: str) -> str:
        title = Str.pascal(name)
        model = title.removesuffix("Resource") or title
        return _TEMPLATE.format(title=title, model=model)
