"""``make:observer`` — generate a model lifecycle observer.

An :class:`arvel.database.Observer` reacts to ORM lifecycle hooks. The
base class is empty; subclasses implement any subset of the hooks below.
Sync hooks (``creating``, ``updating``, ``deleting``) fire inside the
SQLAlchemy event loop; async hooks (``created``, ``updated``, ``deleted``,
``saving``, ``saved``, ``retrieved``) are awaited by Arvel's model layer.

Register with ``MyModel.observe(MyObserver)`` (class — resolved via the app
container when ``DatabaseServiceProvider`` has booted) or
``MyModel.observe(MyObserver())`` (instance).
"""

from __future__ import annotations

from typing import ClassVar

from arvel.console.commands._base_make import BaseMakeCommand
from arvel.support.str import Str

_TEMPLATE = '''"""{title} — model lifecycle observer."""

from __future__ import annotations

from typing import Any

from arvel.database import Observer


class {title}(Observer[Any]):
    """React to ORM lifecycle hooks for a model.

    Replace ``Any`` with your model class for type-safe ``instance`` access.
    Implement only the hooks you care about.
    """

    def creating(self, instance: Any) -> None:
        """Sync — fired before INSERT."""

    async def created(self, instance: Any) -> None:
        """Async — fired after INSERT commits."""

    def updating(self, instance: Any) -> None:
        """Sync — fired before UPDATE."""

    async def updated(self, instance: Any) -> None:
        """Async — fired after UPDATE commits."""

    def deleting(self, instance: Any) -> None:
        """Sync — fired before DELETE."""

    async def deleted(self, instance: Any) -> None:
        """Async — fired after DELETE commits."""
'''


class MakeObserverCommand(BaseMakeCommand):
    name: ClassVar[str] = "make:observer"
    help: ClassVar[str] = "Generate a model lifecycle Observer"
    _target_subdir: ClassVar[str] = "app/observers"

    def _render(self, name: str) -> str:
        return _TEMPLATE.format(title=Str.pascal(name))
