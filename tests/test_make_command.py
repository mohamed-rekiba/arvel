"""make:command — scaffold a console Command (Laravel artisan make:command). The stub subclasses the
real arvel.console.Command (signature/description/handle) and imports against real arvel."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import ModuleType

from arvel.console.generators import generate


def _exec(path: Path, modname: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(modname, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # executes `from arvel.console import Command`
    return module


def test_make_command_stub() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        target = generate("command", "SendReports", base=base)
        assert target == base / "app/commands/send_reports.py"
        src = target.read_text()
        ast.parse(src)
        assert "class SendReports(Command)" in src
        assert "async def handle" in src
        module = _exec(target, "gen_command")
        assert hasattr(module, "SendReports")
