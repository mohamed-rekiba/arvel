"""``make:request`` — generate a typed FormRequest.

A FormRequest pairs a **Pydantic payload model** (the body schema) with
an **authorization hook**. The routing layer parses the request body
into the payload type, constructs the FormRequest, and awaits
:meth:`authorize` before the handler runs.

Access the parsed body inside a handler with ``request.validated()``,
which returns the payload typed as ``T``.
"""

from __future__ import annotations

from typing import ClassVar

from arvel.console.commands._base_make import BaseMakeCommand
from arvel.support.str import Str

_TEMPLATE = '''"""{title} — typed form request."""

from __future__ import annotations

from typing import Any

from arvel.http import FormRequest
from pydantic import BaseModel


class {title}Payload(BaseModel):
    """Body schema for ``{title}``. Add Pydantic fields here."""


class {title}(FormRequest[{title}Payload]):
    """Validated input + authorization gate for the route."""

    async def authorize(self, request: Any) -> bool:
        return True
'''


class MakeRequestCommand(BaseMakeCommand):
    name: ClassVar[str] = "make:request"
    help: ClassVar[str] = "Generate a typed FormRequest (Pydantic payload + authorize)"
    _target_subdir: ClassVar[str] = "app/http/requests"
    _suffix: ClassVar[str] = "Request"

    def _render(self, name: str) -> str:
        return _TEMPLATE.format(title=Str.pascal(name))
