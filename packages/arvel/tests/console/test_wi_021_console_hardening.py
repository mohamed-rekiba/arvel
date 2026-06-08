"""Console hardening: bootstrap, Context expansion, real wire-up, honest deferral.
migrate drives real Alembic (returns N applied count, prints by name)
 migrate:rollback drives Alembic downgrade
 migrate:status lists every revision with applied/pending state
 db:seed runs the named seeder and reports row counts
 route:list resolves Router from container; honest "no routes" on empty
 cache:clear flushes bound store, honest failure when not registered
 cache:forget removes the key, idempotent semantics
 key:rotate honest deferral with tracking-issue pointer (exit 2)
 arvel entrypoint outside-project wrapper points to arvel-new
 discover_commands tolerates any Exception, logs offending entry-point
 arvel.console.bootstrap.bootstrap_framework_application + find_project_root
 Command.needs_application ClassVar opt-in; entrypoint walks-up & boots
 schedule:list and schedule:work honour user's Kernel.schedule via bootstrap
 shell command seeds REPL namespace with app/container/facades
 Context.warn / comment / alert / newline
 Command.call / call_silently delegate to Application.run
 cache_commands no longer swallows Exception in _clear/_forget
"""

from __future__ import annotations

import io
import logging
import sys
import textwrap
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import MagicMock, patch

import pytest
from arvel.console._subsystem import CliSubsystem

# ─────────────────────────────────────────────────────────────────────────────
# — arvel.console.bootstrap module
# ─────────────────────────────────────────────────────────────────────────────


class TestBootstrapModule:
    """The new arvel.console.bootstrap module — lazy framework Application boot."""

    def test_find_project_root_returns_none_when_no_bootstrap_py(self, tmp_path: Path) -> None:
        from arvel.console.bootstrap import find_project_root

        assert find_project_root(tmp_path) is None

    def test_find_project_root_finds_bootstrap_in_cwd(self, tmp_path: Path) -> None:
        from arvel.console.bootstrap import find_project_root

        (tmp_path / "bootstrap").mkdir()
        (tmp_path / "bootstrap" / "app.py").write_text("def create_application(): pass\n")

        assert find_project_root(tmp_path) == tmp_path

    def test_find_project_root_walks_up_to_four_ancestors(self, tmp_path: Path) -> None:
        """walks up to 4 ancestors of start dir."""
        from arvel.console.bootstrap import find_project_root

        (tmp_path / "bootstrap").mkdir()
        (tmp_path / "bootstrap" / "app.py").write_text("def create_application(): pass\n")

        nested = tmp_path / "a" / "b" / "c" / "d"
        nested.mkdir(parents=True)

        assert find_project_root(nested) == tmp_path

    def test_find_project_root_stops_at_depth_five(self, tmp_path: Path) -> None:
        """does not walk infinitely; 5 ancestors deep is missed."""
        from arvel.console.bootstrap import find_project_root

        (tmp_path / "bootstrap").mkdir()
        (tmp_path / "bootstrap" / "app.py").write_text("def create_application(): pass\n")

        too_deep = tmp_path / "a" / "b" / "c" / "d" / "e"
        too_deep.mkdir(parents=True)

        assert find_project_root(too_deep) is None

    def test_bootstrap_returns_none_when_no_project(self, tmp_path: Path) -> None:
        from arvel.console.bootstrap import bootstrap_framework_application

        assert bootstrap_framework_application(tmp_path) is None

    def test_bootstrap_returns_application_when_create_application_present(
        self, tmp_path: Path
    ) -> None:
        from arvel.application import Application

        (tmp_path / "bootstrap").mkdir()
        (tmp_path / "bootstrap" / "app.py").write_text(
            textwrap.dedent(
                """
                from arvel.application import Application

                def create_application():
                    return (
                        Application.configure(base_path="{base}")
                        .with_environment("testing")
                        .with_providers([])
                        .create()
                    )
                """
            ).format(base=tmp_path.as_posix())
        )

        from arvel.console.bootstrap import bootstrap_framework_application

        app = bootstrap_framework_application(tmp_path)
        assert isinstance(app, Application)

    def test_bootstrap_propagates_import_error_from_user_module(self, tmp_path: Path) -> None:
        (tmp_path / "bootstrap").mkdir()
        (tmp_path / "bootstrap" / "app.py").write_text("import nonexistent_module_xyz_42\n")

        from arvel.console.bootstrap import bootstrap_framework_application

        with pytest.raises(ModuleNotFoundError):
            bootstrap_framework_application(tmp_path)

    def test_bootstrap_returns_none_when_create_application_missing(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        (tmp_path / "bootstrap").mkdir()
        (tmp_path / "bootstrap" / "app.py").write_text("# no create_application export\n")

        from arvel.console.bootstrap import bootstrap_framework_application

        with caplog.at_level(logging.WARNING, logger="arvel.console.bootstrap"):
            result = bootstrap_framework_application(tmp_path)
        assert result is None
        assert any("create_application" in r.message for r in caplog.records)


# ─────────────────────────────────────────────────────────────────────────────
# — Command.requires opt-in marker (replaces the legacy needs_application bool)
# ─────────────────────────────────────────────────────────────────────────────


class TestRequiresMarker:
    def test_command_class_default_requires_empty(self) -> None:
        from arvel.console import Command

        assert Command.requires == frozenset()
        assert Command.requires_project_context is False
        assert Command.needs_framework() is False

    def test_command_subclass_can_opt_in_via_requires(self) -> None:
        from arvel.console import Command
        from arvel.console._subsystem import CliSubsystem

        class _NeedsApp(Command):
            name: ClassVar[str] = "needs-app"
            requires: ClassVar[frozenset[CliSubsystem]] = frozenset({CliSubsystem.DATABASE})

            def handle(self, ctx: Any) -> int:
                return 0

        assert _NeedsApp.needs_framework() is True
        assert CliSubsystem.DATABASE in _NeedsApp.requires

    def test_requires_project_context_implies_framework(self) -> None:
        from arvel.console import Command

        class _NeedsRoot(Command):
            name: ClassVar[str] = "needs-root"
            requires_project_context: ClassVar[bool] = True

            def handle(self, ctx: Any) -> int:
                return 0

        assert _NeedsRoot.needs_framework() is True

    def test_command_app_attribute_default_none(self) -> None:
        from arvel.console import Command

        class _Plain(Command):
            name: ClassVar[str] = "plain"

            def handle(self, ctx: Any) -> int:
                return 0

        assert _Plain().app is None


# ─────────────────────────────────────────────────────────────────────────────
# — Context expansion
# ─────────────────────────────────────────────────────────────────────────────


class TestContextExpansion:
    def test_warn_writes_message_to_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        from arvel.console import Context

        Context().warn("careful")
        out = capsys.readouterr().out
        assert "careful" in out

    def test_comment_writes_message_to_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        from arvel.console import Context

        Context().comment("annotation")
        out = capsys.readouterr().out
        assert "annotation" in out

    def test_alert_writes_message_to_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        from arvel.console import Context

        Context().alert("BIG NEWS")
        out = capsys.readouterr().out
        assert "BIG NEWS" in out

    def test_newline_writes_count_blank_lines(self, capsys: pytest.CaptureFixture[str]) -> None:
        from arvel.console import Context

        Context().newline(count=3)
        out = capsys.readouterr().out
        assert out.count("\n") == 3

    def test_newline_default_count_is_one(self, capsys: pytest.CaptureFixture[str]) -> None:
        from arvel.console import Context

        Context().newline()
        out = capsys.readouterr().out
        assert out.count("\n") == 1


# ─────────────────────────────────────────────────────────────────────────────
# — Command.call / call_silently
# ─────────────────────────────────────────────────────────────────────────────


class TestCommandCall:
    def test_call_raises_when_app_not_bound(self) -> None:
        from arvel.console import Command, Context

        class _Plain(Command):
            name: ClassVar[str] = "plain"

            def handle(self, ctx: Context) -> int:
                return 0

        with pytest.raises(RuntimeError, match="requires a bound framework Application"):
            _Plain().call("other")

    def test_call_silently_raises_when_app_not_bound(self) -> None:
        from arvel.console import Command, Context

        class _Plain(Command):
            name: ClassVar[str] = "plain"

            def handle(self, ctx: Context) -> int:
                return 0

        with pytest.raises(RuntimeError, match="requires a bound framework Application"):
            _Plain().call_silently("other")

    def test_call_delegates_to_console_application_run(self) -> None:
        from arvel.console import Application, Command, Context

        invoked: dict[str, int] = {"count": 0}

        class _Target(Command):
            name: ClassVar[str] = "target"

            def handle(self, ctx: Context) -> int:
                invoked["count"] += 1
                return 0

        class _Caller(Command):
            name: ClassVar[str] = "caller"
            requires: ClassVar[frozenset[CliSubsystem]] = frozenset({CliSubsystem.CONFIG})

            def handle(self, ctx: Context) -> int:
                return self.call("target")

        framework_app = MagicMock()
        console_app = Application(commands=[_Target(), _Caller()])
        framework_app.container.make.return_value = console_app

        caller = _Caller()
        caller.app = framework_app  # set as entrypoint would

        code = caller.handle(Context())
        assert code == 0
        assert invoked["count"] == 1

    def test_call_silently_suppresses_stdout(self) -> None:
        from arvel.console import Application, Command, Context

        class _Loud(Command):
            name: ClassVar[str] = "loud"

            def handle(self, ctx: Context) -> int:
                _ = ctx
                sys.stdout.write("LOUD OUTPUT\n")
                return 0

        class _Caller(Command):
            name: ClassVar[str] = "caller"
            requires: ClassVar[frozenset[CliSubsystem]] = frozenset({CliSubsystem.CONFIG})

            def handle(self, ctx: Context) -> int:
                return self.call_silently("loud")

        framework_app = MagicMock()
        console_app = Application(commands=[_Loud(), _Caller()])
        framework_app.container.make.return_value = console_app

        caller = _Caller()
        caller.app = framework_app

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = caller.handle(Context())
        assert code == 0
        assert "LOUD OUTPUT" not in buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# — key:rotate honest deferral
# ─────────────────────────────────────────────────────────────────────────────


class TestKeyRotateHonestDeferral:
    def test_key_rotate_exits_with_not_implemented_message(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from arvel.console import Context
        from arvel.console.commands.key_rotate import KeyRotateCommand

        cmd = KeyRotateCommand()
        code = cmd.handle(Context())
        err = capsys.readouterr().err
        assert code == 2
        assert "not yet implemented" in err.lower()
        assert "workaround" in err.lower()


# ─────────────────────────────────────────────────────────────────────────────
# / / — cache:clear / cache:forget honest behavior
# ─────────────────────────────────────────────────────────────────────────────


class TestCacheCommandsHonest:
    def test_cache_clear_raises_when_facade_unbound(self) -> None:
        """+ : bare-except swallow gone; failure surfaces."""
        import asyncio

        from arvel.console.commands.cache_commands import clear

        with (
            patch("arvel.facades.cache.Cache.store", side_effect=RuntimeError("not bound")),
            pytest.raises(RuntimeError, match="cache subsystem not registered"),
        ):
            asyncio.run(clear(None))

    def test_cache_forget_raises_when_facade_unbound(self) -> None:
        """+ : bare-except swallow gone; failure surfaces."""
        import asyncio

        from arvel.console.commands.cache_commands import forget

        with (
            patch("arvel.facades.cache.Cache.store", side_effect=RuntimeError("not bound")),
            pytest.raises(RuntimeError, match="cache subsystem not registered"),
        ):
            asyncio.run(forget("k", None))


# ─────────────────────────────────────────────────────────────────────────────
# — discover_commands tolerates any Exception
# ─────────────────────────────────────────────────────────────────────────────


class TestDiscoverCommandsWidening:
    def test_load_raises_type_error_does_not_kill_discovery(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from arvel.console import _loader

        good_ep = MagicMock()
        good_ep.name = "good"
        from arvel.console.commands.about import AboutCommand

        good_ep.load.return_value = AboutCommand

        bad_ep = MagicMock()
        bad_ep.name = "bad"
        bad_ep.load.side_effect = TypeError("plugin author messed up")

        with (
            patch(
                "arvel.console._loader.importlib.metadata.entry_points",
                return_value=[good_ep, bad_ep],
            ),
            caplog.at_level(logging.WARNING, logger="arvel.console"),
        ):
            commands = _loader.discover_commands()

        assert len(commands) == 1
        assert commands[0].name == "about"
        assert any("bad" in r.message and "TypeError" in r.message for r in caplog.records)

    def test_instantiation_failure_does_not_kill_discovery(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from arvel.console import _loader

        class _ExplodesOnInit:
            name = "explodes"

            def __init__(self) -> None:
                msg = "construction failed"
                raise ValueError(msg)

        good_ep = MagicMock()
        good_ep.name = "good"
        from arvel.console.commands.about import AboutCommand

        good_ep.load.return_value = AboutCommand

        bad_ep = MagicMock()
        bad_ep.name = "bad-init"
        bad_ep.load.return_value = _ExplodesOnInit

        with (
            patch(
                "arvel.console._loader.importlib.metadata.entry_points",
                return_value=[good_ep, bad_ep],
            ),
            caplog.at_level(logging.WARNING, logger="arvel.console"),
        ):
            commands = _loader.discover_commands()

        assert len(commands) == 1
        assert any("bad-init" in r.message and "ValueError" in r.message for r in caplog.records)


# ─────────────────────────────────────────────────────────────────────────────
# Outside-project wrapper points users at `arvel new`
# ─────────────────────────────────────────────────────────────────────────────


class TestOutsideProjectWrapper:
    def test_main_prints_arvel_new_pointer_and_exits_two_when_no_project(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from arvel.console import entrypoint

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["arvel", "migrate"])

        with pytest.raises(SystemExit) as exc_info:
            entrypoint.main()

        captured = capsys.readouterr()
        assert exc_info.value.code == 2
        assert "arvel new" in captured.err
        assert "No Arvel project found" in captured.err

    def test_main_allows_make_commands_outside_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Outside a project, make:* dispatches by loading only that one command."""
        from arvel.console import entrypoint

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["arvel", "make:controller", "Foo"])

        fake_cmd = MagicMock(owns_process=False)
        with (
            patch.object(entrypoint, "load_command", return_value=fake_cmd) as mock_load,
            patch.object(entrypoint, "Application") as console_cls,
        ):
            typer_app_mock = MagicMock()
            console_cls.return_value = MagicMock(typer_app=typer_app_mock)
            with pytest.raises(SystemExit):
                entrypoint.main()
            mock_load.assert_called_with("make:controller")
            typer_app_mock.assert_called_once()

    def test_main_no_argv_command_allowed_outside_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When invoked with no subcommand (e.g. `arvel`), Typer's --help auto-runs.

        Coverage: the ``project_root is None`` early-return branch.
        """
        from arvel.console import entrypoint

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["arvel"])

        with patch.object(entrypoint, "build_listing_app") as mock_build:
            mock_app = MagicMock()
            mock_build.return_value = mock_app
            with pytest.raises(SystemExit):
                entrypoint.main()
            mock_app.assert_called_once()


class TestInProjectBootstrap:
    """Coverage for the in-project bootstrap dispatch path of ``main``."""

    def _make_project(self, tmp_path: Path) -> Path:
        (tmp_path / "bootstrap").mkdir()
        (tmp_path / "bootstrap" / "app.py").write_text(
            "def create_application():\n    return object()\n"
        )
        return tmp_path

    def test_main_inside_project_boots_for_all_commands(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Bootstrap always runs inside a project — even for non-needs_app commands."""
        from arvel.console import entrypoint
        from arvel.console.commands.key_generate import KeyGenerateCommand

        self._make_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["arvel", "key:generate", "--show"])

        async def _async_noop() -> None:
            return None

        framework_app = MagicMock()
        framework_app.boot = _async_noop
        framework_app.shutdown = _async_noop

        with (
            patch.object(entrypoint, "discover_commands", return_value=[KeyGenerateCommand()]),
            patch.object(
                entrypoint, "bootstrap_framework_application", return_value=framework_app
            ) as mock_bootstrap,
            patch("arvel.console.entrypoint.Application") as console_cls,
        ):
            typer_app_mock = MagicMock()
            console_cls.return_value = MagicMock(typer_app=typer_app_mock)
            entrypoint.main()

            mock_bootstrap.assert_called_once()
            typer_app_mock.assert_called_once()

    def test_main_inside_project_boots_for_needs_app_command(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.console import entrypoint
        from arvel.console.commands.migrate import MigrateCommand

        self._make_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["arvel", "migrate"])

        framework_app = MagicMock()

        async def _async_noop() -> None:
            return None

        framework_app.boot = _async_noop
        framework_app.shutdown = _async_noop

        cmd = MigrateCommand()

        with (
            patch.object(entrypoint, "load_command", return_value=cmd),
            patch.object(entrypoint, "bootstrap_framework_application", return_value=framework_app),
            patch("arvel.console.entrypoint.Application") as console_cls,
        ):
            typer_app_mock = MagicMock()
            console_cls.return_value = MagicMock(typer_app=typer_app_mock)
            entrypoint.main()

            assert cmd.app is framework_app
            typer_app_mock.assert_called_once()

    def test_main_inside_project_bootstrap_returns_none_does_not_attach(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.console import entrypoint
        from arvel.console.commands.migrate import MigrateCommand

        self._make_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["arvel", "migrate"])

        with (
            patch.object(entrypoint, "discover_commands", return_value=[MigrateCommand()]),
            patch.object(entrypoint, "bootstrap_framework_application", return_value=None),
            patch("arvel.console.entrypoint.Application") as console_cls,
        ):
            typer_app_mock = MagicMock()
            console_cls.return_value = MagicMock(typer_app=typer_app_mock)
            entrypoint.main()

            typer_app_mock.assert_called_once()

    def test_main_attaches_provider_commands_from_container(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Integration coverage for _attach_provider_commands: providers seen via container.

        Drives boot via a ``needs_application`` entry-point command so the
        provider-attachment path also runs.
        """
        from arvel.console import Application as ConsoleApp
        from arvel.console import Command, entrypoint
        from arvel.console.commands.migrate import MigrateCommand

        class _Plug(Command):
            name: ClassVar[str] = "plug:hello"

            def handle(self, ctx: Any) -> int:
                return 0

        self._make_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["arvel", "migrate"])

        plug = _Plug()
        framework_app = MagicMock()

        async def _async_noop() -> None:
            return None

        framework_app.boot = _async_noop
        framework_app.shutdown = _async_noop
        framework_app.container.make.return_value = ConsoleApp([plug])

        with (
            patch.object(entrypoint, "discover_commands", return_value=[MigrateCommand()]),
            patch.object(entrypoint, "bootstrap_framework_application", return_value=framework_app),
            patch("arvel.console.entrypoint.Application") as console_cls,
        ):
            typer_app_mock = MagicMock()
            console_cls.return_value = MagicMock(typer_app=typer_app_mock)
            entrypoint.main()

            assert plug.app is framework_app

    def test_main_logs_when_console_service_provider_unbound(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from arvel.console import entrypoint
        from arvel.console.commands.migrate import MigrateCommand

        self._make_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["arvel", "migrate"])

        framework_app = MagicMock()

        async def _async_noop() -> None:
            return None

        framework_app.boot = _async_noop
        framework_app.shutdown = _async_noop
        framework_app.container.make.side_effect = RuntimeError("not bound")

        with (
            patch.object(entrypoint, "discover_commands", return_value=[MigrateCommand()]),
            patch.object(entrypoint, "bootstrap_framework_application", return_value=framework_app),
            patch("arvel.console.entrypoint.Application") as console_cls,
            caplog.at_level(logging.WARNING, logger="arvel.console"),
        ):
            typer_app_mock = MagicMock()
            console_cls.return_value = MagicMock(typer_app=typer_app_mock)
            entrypoint.main()

        assert any("ConsoleServiceProvider" in r.message for r in caplog.records)


# ─────────────────────────────────────────────────────────────────────────────
# — schedule:list / schedule:work honour user Kernel.schedule()
# ─────────────────────────────────────────────────────────────────────────────


class TestSchedulerHonoursUserApp:
    def test_schedule_list_command_opts_into_application(self) -> None:
        """schedule:list declares the SCHEDULER subsystem."""
        from arvel.console.commands.schedule_commands import ScheduleListCommand

        assert ScheduleListCommand.needs_framework() is True
        assert CliSubsystem.SCHEDULER in ScheduleListCommand.requires

    def test_schedule_work_command_opts_into_application(self) -> None:
        from arvel.console.commands.schedule_commands import ScheduleWorkCommand

        assert ScheduleWorkCommand.needs_framework() is True
        assert CliSubsystem.SCHEDULER in ScheduleWorkCommand.requires

    def test_schedule_list_resolves_user_schedule_when_app_bound(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """when app is bound, schedule:list reads container Schedule."""
        from arvel.console import Context
        from arvel.console.commands.schedule_commands import ScheduleListCommand
        from arvel.scheduling import Schedule

        schedule = Schedule()
        schedule.command("my:task").cron("* * * * *")

        framework_app = MagicMock()
        framework_app.container.make.return_value = schedule

        cmd = ScheduleListCommand()
        cmd.app = framework_app
        code = cmd.handle(Context())
        out = capsys.readouterr().out
        assert code == 0
        assert "my:task" in out

    def test_schedule_list_handles_empty_schedule(self, capsys: pytest.CaptureFixture[str]) -> None:
        from arvel.console import Context
        from arvel.console.commands.schedule_commands import ScheduleListCommand
        from arvel.scheduling import Schedule

        framework_app = MagicMock()
        framework_app.container.make.return_value = Schedule()

        cmd = ScheduleListCommand()
        cmd.app = framework_app
        code = cmd.handle(Context())
        out = capsys.readouterr().out
        assert code == 0
        assert "No scheduled tasks" in out

    def test_schedule_list_returns_two_when_app_unbound(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from arvel.console import Context
        from arvel.console.commands.schedule_commands import ScheduleListCommand

        cmd = ScheduleListCommand()
        code = cmd.handle(Context())
        captured = capsys.readouterr()
        assert code == 2
        assert "schedule:list failed" in captured.err

    def test_schedule_work_returns_two_when_app_unbound(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from arvel.console import Context
        from arvel.console.commands.schedule_commands import ScheduleWorkCommand

        cmd = ScheduleWorkCommand()
        code = cmd.handle(Context())
        captured = capsys.readouterr()
        assert code == 2
        assert "schedule:work failed" in captured.err

    def test_schedule_work_invokes_kernel_when_app_bound(self) -> None:
        from unittest.mock import AsyncMock

        from arvel.console import Context
        from arvel.console import _async as _arvel_async
        from arvel.console.commands.schedule_commands import ScheduleWorkCommand

        kernel = MagicMock()
        kernel.run_due_tasks = AsyncMock(return_value=None)
        framework_app = MagicMock()
        framework_app.container.make.return_value = kernel

        cmd = ScheduleWorkCommand()
        cmd.app = framework_app
        code = cmd.handle(Context())
        assert code == 0
        # handle() defers execution via schedule_async; the CLI entrypoint awaits it.
        kernel.run_due_tasks.assert_called_once()
        pending = _arvel_async.get_pending_task()
        assert pending is not None
        pending.close()  # prevent RuntimeWarning: coroutine never awaited
        _arvel_async.clear_pending_task()

    def test_run_loop_once_calls_run_due_tasks(self) -> None:
        import asyncio
        from unittest.mock import AsyncMock

        from arvel.console.commands.schedule_commands import run_loop

        kernel = MagicMock()
        kernel.run_due_tasks = AsyncMock(return_value=None)
        kernel.serve_forever = AsyncMock(return_value=None)

        asyncio.run(run_loop(kernel, once=True, sleep=1.0, max_failures=None))

        kernel.run_due_tasks.assert_awaited_once()
        kernel.serve_forever.assert_not_called()

    def test_run_loop_continuous_calls_serve_forever(self) -> None:
        import asyncio
        from unittest.mock import AsyncMock

        from arvel.console.commands.schedule_commands import run_loop

        kernel = MagicMock()
        kernel.run_due_tasks = AsyncMock(return_value=None)
        kernel.serve_forever = AsyncMock(return_value=None)

        asyncio.run(run_loop(kernel, once=False, sleep=1.0, max_failures=3))

        kernel.serve_forever.assert_awaited_once_with(sleep_seconds=1.0, max_failures=3)
        kernel.run_due_tasks.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# — shell seeds REPL namespace with framework facades
# ─────────────────────────────────────────────────────────────────────────────


class TestShellNamespace:
    def test_shell_command_owns_process_and_self_bootstraps(self) -> None:
        from arvel.console.commands.shell import ShellCommand

        # shell drives its own event loop (IPython autoawait + prompt_toolkit
        # both call asyncio.run), so it must run outside the entrypoint's
        # asyncio.run wrapper and bootstrap the framework itself. owns_process
        # (not needs_framework) is the lever that routes it out of async_main,
        # so the entrypoint never pre-boots it even though it declares requires.
        assert ShellCommand.owns_process is True

    def test_bootstrap_app_includes_app_and_container(self) -> None:
        from arvel.console.commands.shell import ShellCommand
        from arvel.container.errors import BindingResolutionError
        from sqlalchemy.ext.asyncio import async_sessionmaker

        cmd = ShellCommand()
        framework_app = MagicMock()
        # Refuse session-maker resolution so this test stays scoped to the
        # app/container assertions — session binding gets its own dedicated
        # tests below.
        framework_app.container.make.side_effect = BindingResolutionError((async_sessionmaker,))
        cmd.app = framework_app
        try:
            ns = cmd.build_namespace()
            assert "app" in ns
            assert "container" in ns
            assert ns["app"] is framework_app
            assert ns["container"] is framework_app.container
            assert "session" not in ns
        finally:
            cmd.release_active_session()

    def test_bootstrap_app_includes_facades(self) -> None:
        from arvel.console.commands.shell import ShellCommand
        from arvel.container.errors import BindingResolutionError
        from sqlalchemy.ext.asyncio import async_sessionmaker

        cmd = ShellCommand()
        framework_app = MagicMock()
        framework_app.container.make.side_effect = BindingResolutionError((async_sessionmaker,))
        cmd.app = framework_app
        try:
            ns = cmd.build_namespace()
            assert "Cache" in ns
            assert "Auth" in ns
        finally:
            cmd.release_active_session()

    def test_bootstrap_app_omits_session_when_database_provider_missing(self) -> None:
        """+ (this fix): graceful skip when no ``DatabaseServiceProvider``.

        CLI-only apps (no database wired up) should still get a working REPL
        just without the ``session`` binding. ``BindingResolutionError`` from
        ``container.make(async_sessionmaker[...])`` must be swallowed and the
        namespace returned cleanly.
        """
        from arvel.console.commands.shell import ShellCommand
        from arvel.container.errors import BindingResolutionError
        from arvel.database.session import get_optional_session
        from sqlalchemy.ext.asyncio import async_sessionmaker

        cmd = ShellCommand()
        framework_app = MagicMock()
        framework_app.container.make.side_effect = BindingResolutionError((async_sessionmaker,))
        cmd.app = framework_app
        try:
            ns = cmd.build_namespace()
            assert "session" not in ns
            # And the active-session ContextVar was NOT polluted as a side effect.
            assert get_optional_session() is None
        finally:
            cmd.release_active_session()

    def test_bootstrap_app_binds_session_when_database_provider_registered(
        self, tmp_path: Path
    ) -> None:
        """The core fix for the ``arvel tinker`` ``NoActiveSessionError`` regression.

        With ``DatabaseServiceProvider`` registered on the framework
        ``Application``, ``build_namespace`` MUST:

        1. Expose ``session`` in the REPL namespace.
        2. Push that same session onto the active-session ContextVar so
        ``get_active_session`` (and therefore ``User.first`` & friends)
        returns it inside the REPL.
        """
        import os

        from arvel.application import ApplicationBuilder
        from arvel.console.commands.shell import ShellCommand
        from arvel.database.session import get_active_session
        from arvel.providers import ConfigServiceProvider, DatabaseServiceProvider
        from sqlalchemy.ext.asyncio import AsyncSession

        snapshot = dict(os.environ)
        os.environ["DB_CONNECTION"] = "memory"

        try:
            framework_app = (
                ApplicationBuilder(base_path=tmp_path)
                .with_providers([ConfigServiceProvider, DatabaseServiceProvider])
                .create()
            )
            cmd = ShellCommand()
            cmd.app = framework_app
            try:
                ns = cmd.build_namespace()
                assert "session" in ns, ns.keys()
                assert isinstance(ns["session"], AsyncSession)
                # ContextVar is populated with the SAME session object.
                assert get_active_session() is ns["session"]
            finally:
                cmd.release_active_session()
        finally:
            os.environ.clear()
            os.environ.update(snapshot)

    def test_release_active_session_resets_contextvar_and_closes(self, tmp_path: Path) -> None:
        """``release_active_session`` must be safe and idempotent.

        Called from the REPL ``finally`` block, it has to:

        - Reset the ContextVar (so the next test / next REPL run starts clean).
        - Close the session (release the connection back to the pool).
        - No-op gracefully on a second call.
        """
        import os

        from arvel.application import ApplicationBuilder
        from arvel.console.commands.shell import ShellCommand
        from arvel.database.session import get_optional_session
        from arvel.providers import ConfigServiceProvider, DatabaseServiceProvider

        snapshot = dict(os.environ)
        os.environ["DB_CONNECTION"] = "memory"

        try:
            framework_app = (
                ApplicationBuilder(base_path=tmp_path)
                .with_providers([ConfigServiceProvider, DatabaseServiceProvider])
                .create()
            )
            cmd = ShellCommand()
            cmd.app = framework_app
            cmd.build_namespace()
            assert get_optional_session() is not None

            cmd.release_active_session()
            assert get_optional_session() is None

            # Idempotent: second call is a no-op.
            cmd.release_active_session()
            assert get_optional_session() is None
        finally:
            os.environ.clear()
            os.environ.update(snapshot)


# ─────────────────────────────────────────────────────────────────────────────
# — route:list resolves Router from container; honest empty table
# ─────────────────────────────────────────────────────────────────────────────


class TestRouteListResolution:
    def test_get_routes_returns_empty_without_app(self) -> None:
        from arvel.console.commands.route_list import RouteListCommand

        cmd = RouteListCommand()
        assert cmd.get_routes() == []

    def test_get_routes_returns_empty_when_router_missing(self) -> None:
        from arvel.console.commands.route_list import RouteListCommand

        framework_app = MagicMock()
        framework_app.container.make.side_effect = RuntimeError("not bound")

        cmd = RouteListCommand()
        cmd.app = framework_app
        assert cmd.get_routes() == []

    def test_get_routes_delegates_to_router(self) -> None:
        from arvel.console.commands.route_list import RouteListCommand
        from arvel.routing import RouteSpec

        async def _handler() -> None: ...

        spec = RouteSpec(method="GET", path="/foo", handler=_handler)
        router = MagicMock()
        router.routes.return_value = [spec]

        framework_app = MagicMock()
        framework_app.container.make.return_value = router

        cmd = RouteListCommand()
        cmd.app = framework_app
        assert cmd.get_routes() == [spec]

    def test_route_list_command_opts_into_application(self) -> None:
        from arvel.console.commands.route_list import RouteListCommand

        assert RouteListCommand.needs_framework() is True
        assert CliSubsystem.HTTP in RouteListCommand.requires

    def test_register_callback_prints_no_routes_when_empty(self) -> None:
        import typer
        from arvel.console.commands.route_list import RouteListCommand
        from typer.testing import CliRunner

        cmd = RouteListCommand()  # no app bound → empty list
        app = typer.Typer()
        cmd.register(app)
        runner = CliRunner()
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "no routes registered" in result.output
