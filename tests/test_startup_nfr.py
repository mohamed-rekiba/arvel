"""G2 — startup performance NFR.

The load-bearing invariant: ``import arvel`` must pull in **zero** heavy libraries.
This is what lets the framework stay light and the CLI fast. Measured in a clean
subprocess (the current process has already imported things under pytest).

See knowledge/port/00-porting-strategy.md §5b.
"""

from __future__ import annotations

import subprocess
import sys

# Libraries that must NEVER be imported merely by `import arvel`.
HEAVY_LIBS = ("litestar", "sqlalchemy", "taskiq", "PIL", "pydantic", "rich", "typer", "click")


def _modules_after(code: str) -> set[str]:
    """Run `code` in a clean interpreter and return the top-level module names loaded."""
    script = (
        code + "\nimport sys, json; print(json.dumps(sorted(m.split('.')[0] for m in sys.modules)))"
    )
    out = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )
    import json

    return set(json.loads(out.stdout.strip().splitlines()[-1]))


def test_import_arvel_pulls_no_heavy_libs() -> None:
    loaded = _modules_after("import arvel")
    leaked = sorted(set(HEAVY_LIBS) & loaded)
    assert not leaked, f"`import arvel` leaked heavy libraries: {leaked}"


def test_importtime_shows_no_heavy_libs() -> None:
    """Reinforce via the very mechanism the NFR names: `python -X importtime`."""
    proc = subprocess.run(
        [sys.executable, "-X", "importtime", "-c", "import arvel"],
        capture_output=True,
        text=True,
        check=True,
    )
    trace = proc.stderr  # importtime writes to stderr
    for lib in HEAVY_LIBS:
        assert f" {lib}" not in trace and f"\t{lib}" not in trace, (
            f"importtime trace shows heavy lib {lib!r} imported on `import arvel`"
        )


def test_t0_version_path_imports_no_heavy_libs() -> None:
    """The T0 CLI fast path (`arvel --version`) must answer before importing typer/click or
    any framework/heavy lib — that's what keeps cold-start under the budget."""
    loaded = _modules_after(
        "import sys; sys.argv = ['arvel', '--version']\nfrom arvel.console import main\nmain()"
    )
    leaked = sorted(set(HEAVY_LIBS) & loaded)
    assert not leaked, f"the `arvel --version` fast path leaked heavy/framework libs: {leaked}"


def test_version_is_a_string() -> None:
    import arvel

    assert isinstance(arvel.__version__, str)
    assert arvel.__version__
