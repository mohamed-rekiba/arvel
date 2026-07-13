"""Seeder console output (doc 13) — a seeder gets the same output surface a command has, so long
seeds can render a progress bar and section lines. Injected by the ``db:seed`` runner; a silent
no-op until then."""

from __future__ import annotations

import asyncio
import io

from arvel.console import ConsoleOutput
from arvel.database import Seeder
from arvel.database.seeder import _NULL_OUTPUT


def test_progress_bar_null_output_iterates_every_item_silently() -> None:
    # a seeder run outside db:seed keeps the default no-op output: no rendering, but the loop still
    # runs for every item (with_progress_bar just yields them through).
    processed: list[int] = []

    class S(Seeder):
        async def run(self) -> None:
            for i in self.with_progress_bar([1, 2, 3], label="items"):
                await asyncio.sleep(0)  # the body may await; the bar advances as items are consumed
                processed.append(i)

    asyncio.run(S().run())
    assert processed == [1, 2, 3]


def test_injected_output_renders_lines_and_still_iterates() -> None:
    out, err = io.StringIO(), io.StringIO()
    processed: list[int] = []

    class S(Seeder):
        async def run(self) -> None:
            self.line("→ items")
            self.info("seeding")
            for i in self.with_progress_bar([1, 2], label="items"):
                processed.append(i)

    s = S()
    s.output = ConsoleOutput(out, err)
    asyncio.run(s.run())

    assert processed == [1, 2]
    assert "→ items" in out.getvalue()
    assert "seeding" in out.getvalue()


def test_child_seeders_inherit_the_parent_output() -> None:
    out = io.StringIO()

    class Child(Seeder):
        async def run(self) -> None:
            self.line("child ran")

    class Parent(Seeder):
        async def run(self) -> None:
            await self.call(Child)

    p = Parent()
    p.output = ConsoleOutput(out, io.StringIO())
    asyncio.run(p.run())

    assert "child ran" in out.getvalue()  # the child wrote to the parent's injected sink


def test_call_once_children_inherit_the_parent_output() -> None:
    from arvel.database.seeder import reset_called_once

    out = io.StringIO()

    class Once(Seeder):
        async def run(self) -> None:
            self.line("once")

    class Parent(Seeder):
        async def run(self) -> None:
            await self.call_once(Once)

    reset_called_once()
    p = Parent()
    p.output = ConsoleOutput(out, io.StringIO())
    asyncio.run(p.run())

    assert "once" in out.getvalue()


def test_seeder_output_defaults_to_the_shared_null_singleton() -> None:
    class S(Seeder):
        async def run(self) -> None: ...

    assert S().output is _NULL_OUTPUT
