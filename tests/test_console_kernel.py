"""Console boot kernel: an app-dependent command boots the project app.

Drives the real path through `run_app_command`: load a temp project's bootstrap/app.py, boot it
(sync bootstrap + async boot, one event loop), run the command, terminate.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from arvel.kernel import Application, set_application

# terminating hook writes a sentinel file so tests can prove terminate() ran; `{boot}` optionally
# splices in a provider whose async boot() raises, to test the boot-failure path.
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
        route_list()
    finally:
        set_application(None)

    out = capsys.readouterr().out
    assert "/ping" in out


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
    """Handler failure exits cleanly (typer.Exit) but terminate still runs; ARVEL_DEBUG re-raises."""
    import typer

    _write_project(tmp_path, bad_boot=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ARVEL_DEBUG", raising=False)
    from arvel.console.kernel import run_app_command

    try:
        with pytest.raises(typer.Exit):  # concise exit, not the RuntimeError traceback
            run_app_command(_boom_handler)
        assert (tmp_path / "terminated.flag").exists()  # finally → terminate ran
    finally:
        set_application(None)


def test_arvel_debug_reraises_the_original_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_project(tmp_path, bad_boot=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ARVEL_DEBUG", "1")
    from arvel.console.kernel import run_app_command

    try:
        with pytest.raises(RuntimeError, match="handler boom"):  # full traceback path
            run_app_command(_boom_handler)
    finally:
        set_application(None)


def test_terminate_runs_on_boot_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import typer

    _write_project(tmp_path, bad_boot=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ARVEL_DEBUG", raising=False)
    from arvel.console.kernel import run_app_command

    try:
        with pytest.raises(typer.Exit):
            run_app_command(_noop_handler)
        assert (tmp_path / "terminated.flag").exists()  # failed boot still terminated
    finally:
        set_application(None)


# -- Artisan.call / call_silently (CLI-5) -------------------------------------------------------


def test_artisan_call_runs_a_builtin_and_returns_its_exit_code() -> None:
    from arvel.console.kernel import Artisan

    assert Artisan.call("extras") == 0


def test_artisan_call_returns_the_command_s_typer_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from arvel.console.kernel import Artisan

    monkeypatch.chdir(tmp_path)
    (tmp_path / "taken").mkdir()
    assert Artisan.call("new", ["taken"]) == 1  # `new` exits 1 when the target already exists


def test_artisan_call_silently_suppresses_output(capsys: pytest.CaptureFixture[str]) -> None:
    from arvel.console.kernel import Artisan

    assert Artisan.call_silently("extras") == 0
    assert capsys.readouterr().out == ""


@pytest.fixture
def app() -> Iterator[Application]:
    application = Application()
    set_application(application)
    yield application
    set_application(None)


def test_artisan_call_dispatches_an_app_registered_closure(app: Application) -> None:
    from arvel import Console
    from arvel.console.kernel import Artisan

    ran: list[str] = []

    async def greet(name: str) -> None:
        ran.append(name)

    Console.command("greet {name}", greet)
    assert Artisan.call("greet", {"name": "Ada"}) == 0
    assert ran == ["Ada"]


def test_artisan_call_dispatches_an_app_registered_command_class(app: Application) -> None:
    from arvel.console import Command
    from arvel.console.kernel import Artisan

    seen: dict[str, object] = {}

    class Notify(Command):
        signature = "notify {user} {--force}"

        async def handle(self) -> None:
            seen["user"] = self.argument("user")
            seen["force"] = self.option("force")

    app.command_classes.append(Notify)
    assert Artisan.call("notify", {"user": "Ada", "--force": True}) == 0
    assert seen == {"user": "Ada", "force": True}


def test_artisan_call_without_an_active_app_errors_clearly() -> None:
    from arvel.console.kernel import Artisan

    with pytest.raises(RuntimeError, match="no active application"):
        Artisan.call("some:app-registered-command")


def test_artisan_call_unknown_command_raises(app: Application) -> None:
    from arvel.console.kernel import Artisan

    with pytest.raises(ValueError, match="is not defined"):
        Artisan.call("totally-unknown-command")
