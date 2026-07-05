"""Console (doc 13) — db:seed runs the app's root seeder."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from arvel.console import build_cli
from arvel.database import Seeder

runner = CliRunner()


def test_db_seed_runs_root_seeder() -> None:
    from arvel.kernel import Application, set_application

    ran: list[str] = []

    class RootSeeder(Seeder):
        async def run(self) -> None:
            ran.append("seeded")

    app = Application()
    app.instance("seeder", RootSeeder())
    set_application(app)
    try:
        result = runner.invoke(build_cli(), ["db:seed"])
        assert result.exit_code == 0
        assert ran == ["seeded"]
    finally:
        set_application(None)


def test_db_seed_injects_a_live_console_output_into_the_seeder() -> None:
    from arvel.console import ConsoleOutput
    from arvel.database.seeder import _NULL_OUTPUT
    from arvel.kernel import Application, set_application

    class RootSeeder(Seeder):
        async def run(self) -> None: ...

    seeder = RootSeeder()
    assert seeder.output is _NULL_OUTPUT  # silent until the runner injects a console

    app = Application()
    app.instance("seeder", seeder)
    set_application(app)
    try:
        result = runner.invoke(build_cli(), ["db:seed"])
        assert result.exit_code == 0
        assert isinstance(seeder.output, ConsoleOutput)  # runner swapped in a live console
    finally:
        set_application(None)


def test_db_seed_without_binding_errors() -> None:
    from arvel.kernel import Application, set_application

    set_application(Application())  # active app, but no 'seeder' bound → binding-missing branch
    try:
        result = runner.invoke(build_cli(), ["db:seed"])
        assert result.exit_code == 1
        assert "no seeder bound" in result.output
    finally:
        set_application(None)


def test_db_seed_runs_seeder_through_full_lifecycle(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    # project path (no ambient app): db:seed boots the app from bootstrap/app.py then runs the seeder
    from pathlib import Path

    from arvel.kernel import set_application

    root = Path(str(tmp_path))
    (root / "bootstrap").mkdir()
    (root / "bootstrap" / "app.py").write_text(
        "from pathlib import Path\n"
        "from arvel.kernel import Application\n"
        "from arvel.database import Seeder\n\n"
        "class RootSeeder(Seeder):\n"
        "    async def run(self):\n"
        "        Path('seeded.flag').write_text('1')\n\n"
        "def create_app():\n"
        "    app = Application(base_path='.')\n"
        "    app.instance('seeder', RootSeeder())\n"
        "    return app\n"
    )
    monkeypatch.chdir(root)
    try:
        result = runner.invoke(build_cli(), ["db:seed"])
        assert result.exit_code == 0, result.output
        assert (root / "seeded.flag").exists()  # booted via the kernel + seeder ran
    finally:
        set_application(None)
