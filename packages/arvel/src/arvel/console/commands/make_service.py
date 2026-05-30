"""``make:service`` — generate a service class.

Arvel does not ship a framework ``Service`` base class. The convention
is a plain Python class in ``app/services/`` whose constructor takes
its dependencies — those can then be resolved through the container,
either by binding the service and using :func:`arvel.dep` in a route
handler, or by injecting collaborators via a service provider's
``register()``.
"""

from __future__ import annotations

from typing import ClassVar

from arvel.console.commands._base_make import BaseMakeCommand
from arvel.support.str import Str

_TEMPLATE = '''"""{title} — application service."""

from __future__ import annotations


class {title}:
    """Encapsulates a unit of business logic.

    Constructor parameters are resolved by Arvel's container when
    this service is bound and injected via ``dep({title})``.
    """

    def __init__(self) -> None:
        pass
'''


class MakeServiceCommand(BaseMakeCommand):
    name: ClassVar[str] = "make:service"
    help: ClassVar[str] = "Generate an application service class"
    _target_subdir: ClassVar[str] = "app/services"

    def _render(self, name: str) -> str:
        return _TEMPLATE.format(title=Str.pascal(name))
