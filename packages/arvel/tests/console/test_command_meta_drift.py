"""Guards for the generated `arvel --help` manifest (``console/_command_meta.py``).

Two things must hold:
1. The checked-in manifest matches the live commands (no stale help text).
2. Rendering the top-level listing doesn't import the heavy framework stack —
   that's the whole point of the manifest.
"""

from __future__ import annotations

import subprocess
import sys

from arvel.console._command_meta import COMMAND_HELP
from arvel.console._loader import discover_commands, entry_point_names
from arvel.console.entrypoint import build_listing_app
from typer.testing import CliRunner


def _live_command_help() -> dict[str, str]:
    return dict(sorted((c.name, (c.help or "").strip()) for c in discover_commands()))


def test_manifest_matches_live_commands() -> None:
    """If this fails, run: uv run python scripts/gen_command_meta.py"""
    assert _live_command_help() == COMMAND_HELP


def test_listing_app_lists_every_command() -> None:
    result = CliRunner().invoke(build_listing_app(), ["--help"])
    assert result.exit_code == 0
    for name in entry_point_names():
        assert name in result.stdout


def test_listing_app_does_not_import_heavy_stack() -> None:
    """Building + rendering the listing must not pull in SQLAlchemy/FastAPI/etc."""
    code = (
        "import sys\n"
        "from typer.testing import CliRunner\n"
        "from arvel.console.entrypoint import build_listing_app\n"
        "CliRunner().invoke(build_listing_app(), ['--help'])\n"
        "heavy = [m for m in ('sqlalchemy', 'fastapi', 'starlette', 'jinja2') "
        "if m in sys.modules]\n"
        "print(','.join(heavy))\n"
    )
    proc = subprocess.run(  # noqa: S603 - fixed code string + sys.executable, no external input
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc.stdout.strip() == "", f"listing imported heavy modules: {proc.stdout.strip()}"
