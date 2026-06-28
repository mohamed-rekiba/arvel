"""arvel.http.Response — a light, engine-agnostic response value.

Handlers may return a plain ``dict``/``list``/``str`` (Litestar serializes it) or
an explicit ``Response``; the kernel converts the latter to a ``litestar.Response``
in the serve path (Litestar imported there, not here).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Response:
    content: Any = None
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict[str, str])


def json(content: Any, status: int = 200) -> Response:
    return Response(content=content, status=status)
