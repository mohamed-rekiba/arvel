"""Command I/O (CLI-2): ConsoleOutput — stdout/stderr separation, table, progress bar; no bare
`print()` left in `Command` (built on click's echo/style/progressbar — `arvel.console` may not
import `rich`, see import-linter's G2 contract)."""

from __future__ import annotations

import io
import re
import subprocess
import sys
from pathlib import Path

from arvel.console import Command, ConsoleOutput


def test_info_line_comment_question_go_to_stdout() -> None:
    out, err = io.StringIO(), io.StringIO()
    console = ConsoleOutput(out, err)
    console.info("hello")
    console.line("a line")
    console.comment("a comment")
    console.question("a question?")
    assert out.getvalue() == "hello\na line\na comment\na question?\n"
    assert err.getvalue() == ""


def test_error_and_warn_go_to_stderr() -> None:
    out, err = io.StringIO(), io.StringIO()
    console = ConsoleOutput(out, err)
    console.error("boom")
    console.warn("careful")
    assert out.getvalue() == ""
    assert "boom" in err.getvalue()
    assert "careful" in err.getvalue()


def test_new_line() -> None:
    out = io.StringIO()
    ConsoleOutput(out, io.StringIO()).new_line(2)
    assert out.getvalue() == "\n\n"


def test_table_renders_headers_and_rows() -> None:
    out = io.StringIO()
    ConsoleOutput(out, io.StringIO()).table(["id", "name"], [[1, "Ada"], [2, "Grace"]])
    rendered = out.getvalue()
    assert "id" in rendered and "name" in rendered
    assert "Ada" in rendered and "Grace" in rendered


def test_with_progress_bar_advances_over_the_iterable() -> None:
    out = io.StringIO()
    console = ConsoleOutput(out, io.StringIO())
    seen = list(console.with_progress_bar([1, 2, 3]))
    assert seen == [1, 2, 3]


def test_command_delegates_io_to_its_injected_output() -> None:
    out, err = io.StringIO(), io.StringIO()

    class Greet(Command):
        async def handle(self) -> None:
            self.info("hi")
            self.error("nope")

    cmd = Greet(output=ConsoleOutput(out, err))
    import asyncio

    asyncio.run(cmd.handle())
    assert out.getvalue() == "hi\n"
    assert "nope" in err.getvalue()


def test_no_bare_print_left_in_the_console_package() -> None:
    """Grep-clean AC — the only remaining bare `print()`s are the deliberate T0 fast paths
    (`--version`/the banner), which must import neither typer nor rich/click."""
    console_dir = Path(__file__).resolve().parents[1] / "src" / "arvel" / "console"
    allowed = {console_dir / "__init__.py", console_dir / "banner.py"}
    offenders: list[str] = []
    for path in console_dir.rglob("*.py"):
        if "_skeleton" in path.parts or path in allowed:
            continue
        if re.search(r"(?<!\w)print\(", path.read_text()):
            offenders.append(str(path))
    assert offenders == []


def test_version_fast_path_still_imports_no_click_or_rich() -> None:
    """ConsoleOutput's click import must stay inside methods — `--version` must not drag it in."""
    proc = subprocess.run(
        [sys.executable, "-X", "importtime", "-m", "arvel.console", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    for lib in ("click", "rich"):
        assert f" {lib}" not in proc.stderr, f"--version eagerly imported {lib!r}"
