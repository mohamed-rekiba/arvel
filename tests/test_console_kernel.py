"""Console boot kernel (foundation It.5a — CLI-1): an app-dependent command boots the project app.

Drives the real path — a temp project with bootstrap/app.py (create_app factory) + a route file — and
runs `route:list` through ``run_app_command``, which loads the app, boots it (sync bootstrap + async
boot, one event loop), runs the command, and terminates.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from arvel.kernel import set_application

# bootstrap/app.py whose terminating hook writes a sentinel file, so a test can prove terminate() ran.
# `{boot}` is spliced in to optionally add a provider whose async boot() raises (the M7 boot-failure).
_BOOTSTRAP_WITH_TERMINATE_SENTINEL = """
from pathlib import Path
from arvel.kernel import Application
from arvel.kernel.service_provider import ServiceProvider

class TermProvider(ServiceProvider):
    def register(self):
        self.app.terminating(lambda: Path("terminated.flag").write_text("1"))
{boot}
def create_app():
    app = Application(base_path=".")
    app.app_provider_classes.append(TermProvider)
{append_boot}
    return app
"""

_BAD_BOOT_PROVIDER = """
class BadBoot(ServiceProvider):
    async def boot(self):
        raise RuntimeError("boot boom")
"""


async def _boom_handler(_app: object) -> None:
    raise RuntimeError("handler boom")


async def _noop_handler(_app: object) -> None:
    return None


def _scaffold_project(root: Path) -> None:
    (root / "bootstrap").mkdir()
    (root / "bootstrap" / "app.py").write_text(
        "from arvel.kernel import Application\n\n"
        "def create_app():\n"
        "    app = Application(base_path='.')\n"
        "    app.route_files.append('routes/web.py')\n"
        "    return app\n"
    )
    (root / "routes").mkdir()
    (root / "routes" / "web.py").write_text(
        "from arvel import Route\n\nRoute.get('/ping', lambda request: {'pong': True})\n"
    )


def test_route_list_boots_app_and_lists_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _scaffold_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    from arvel.console.routes import route_list

    try:
        route_list()  # → run_app_command: load create_app → boot → list routes → terminate
    finally:
        set_application(None)

    out = capsys.readouterr().out
    assert "/ping" in out  # the route file was imported into the booted app and listed


def test_app_command_outside_a_project_exits_clearly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import typer

    monkeypatch.chdir(tmp_path)  # no bootstrap/app.py here
    from arvel.console.routes import route_list

    with pytest.raises(typer.Exit):
        route_list()


def test_load_project_app_returns_none_without_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from arvel.console.kernel import load_project_app

    monkeypatch.chdir(tmp_path)
    assert load_project_app() is None


def test_create_app_error_propagates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "bootstrap").mkdir()
    (tmp_path / "bootstrap" / "app.py").write_text(
        "def create_app():\n    raise RuntimeError('factory boom')\n"
    )
    monkeypatch.chdir(tmp_path)
    from arvel.console.kernel import load_project_app

    with pytest.raises(RuntimeError, match="factory boom"):  # surfaces, not misreported as None
        load_project_app()


def _write_project(root: Path, *, bad_boot: bool) -> None:
    (root / "bootstrap").mkdir()
    (root / "bootstrap" / "app.py").write_text(
        _BOOTSTRAP_WITH_TERMINATE_SENTINEL.format(
            boot=_BAD_BOOT_PROVIDER if bad_boot else "",
            append_boot="    app.app_provider_classes.append(BadBoot)\n" if bad_boot else "",
        )
    )


def test_terminate_runs_when_handler_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_project(tmp_path, bad_boot=False)
    monkeypatch.chdir(tmp_path)
    from arvel.console.kernel import run_app_command

    try:
        with pytest.raises(RuntimeError, match="handler boom"):
            run_app_command(_boom_handler)
        assert (tmp_path / "terminated.flag").exists()  # finally → terminate ran
    finally:
        set_application(None)


def test_terminate_runs_on_boot_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_project(tmp_path, bad_boot=True)
    monkeypatch.chdir(tmp_path)
    from arvel.console.kernel import run_app_command

    try:
        with pytest.raises(RuntimeError, match="boot boom"):
            run_app_command(_noop_handler)
        assert (tmp_path / "terminated.flag").exists()  # M7: failed boot still terminated
    finally:
        set_application(None)
