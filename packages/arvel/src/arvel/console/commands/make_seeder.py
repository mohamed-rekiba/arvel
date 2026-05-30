"""``make:seeder`` — generate a database seeder.

Seeders subclass :class:`arvel.database.Seeder` and implement an
``async run()`` method. The CLI's ``db:seed`` command discovers seeders
by class name from ``database/seeders/*.py`` and executes ``run()``
inside a managed transaction — your seeder should **not** call
``commit()``; the caller owns the transaction.

A typical seeder uses factories or raw inserts:

    from app.models.post import Post
    from database.factories.post_factory import PostFactory

    class PostSeeder(Seeder):
        async def run(self) -> None:
            await PostFactory().count(10).create()

For an entrypoint that runs other seeders, name it ``DatabaseSeeder``
and use ``self.call(OtherSeeder())``.
"""

from __future__ import annotations

from typing import ClassVar

from arvel.console.commands._base_make import BaseMakeCommand
from arvel.support.str import Str

_TEMPLATE = '''"""{title} — database seeder."""

from __future__ import annotations

from arvel.database import Seeder


class {title}(Seeder):
    """Populates rows for development and test environments."""

    async def run(self) -> None:
        # Insert rows here — do not call commit(), the framework manages it.
        return None
'''


class MakeSeederCommand(BaseMakeCommand):
    name: ClassVar[str] = "make:seeder"
    help: ClassVar[str] = "Generate a database seeder (arvel.database.Seeder)"
    _target_subdir: ClassVar[str] = "database/seeders"

    def _render(self, name: str) -> str:
        return _TEMPLATE.format(title=Str.pascal(name))
