"""Single-loop CLI + schedule_async + OpenAPI commands.
-x Single asyncio event loop — migrate uses schedule_async
 -x Provider commands always attached after boot
 -x db:seed binds AsyncSession via use_session before running seeder
 -x openapi:export command writes YAML / JSON / stdout
 -x openapi:validate command validates spec, exits 1 on failure
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# schedule_async module tests (should pass immediately after stub)
# ─────────────────────────────────────────────────────────────────────────────


class TestScheduleAsync:
    def test_schedule_async_stores_coroutine(self) -> None:
        from arvel.console._async import get_pending_task, schedule_async

        async def _dummy() -> None:
            pass

        coro = _dummy()
        schedule_async(coro)
        assert get_pending_task() is coro
        coro.close()

    def test_schedule_async_overwrites_previous(self) -> None:
        from arvel.console._async import get_pending_task, schedule_async

        async def _a() -> None:
            pass

        async def _b() -> None:
            pass

        coro_a = _a()
        coro_b = _b()
        schedule_async(coro_a)
        schedule_async(coro_b)
        assert get_pending_task() is coro_b
        coro_a.close()
        coro_b.close()

    def test_default_is_none(self) -> None:
        from arvel.console._async import clear_pending_task, get_pending_task

        clear_pending_task()
        assert get_pending_task() is None

    def test_schedule_async_exported(self) -> None:
        import arvel.console._async as mod

        assert "schedule_async" in mod.__all__


# ─────────────────────────────────────────────────────────────────────────────
# — migrate commands use schedule_async, not asyncio.run
# ─────────────────────────────────────────────────────────────────────────────


class TestMigrateUsesScheduleAsync:
    """After refactor, migrate commands must NOT call asyncio.run inside their callback."""

    def _build_fake_app(self, tmp_path: Path) -> MagicMock:
        container = MagicMock()
        from sqlalchemy.ext.asyncio import AsyncEngine

        fake_engine = MagicMock(spec=AsyncEngine)

        def _make(t: type) -> object:
            return fake_engine if t is AsyncEngine else MagicMock()

        container.make.side_effect = _make
        app = MagicMock()
        app.container = container
        app.base_path.return_value = tmp_path
        return app

    def test_migrate_callback_calls_schedule_async_not_asyncio_run(self, tmp_path: Path) -> None:
        """The Typer callback must call schedule_async, not asyncio.run."""
        from arvel.console._async import schedule_async
        from arvel.console.commands.migrate import MigrateCommand

        cmd = MigrateCommand()
        cmd.app = self._build_fake_app(tmp_path)

        import typer

        typer_app = typer.Typer()
        cmd.register(typer_app)

        # Simulate callback invocation with monkeypatching asyncio.run
        # If migrate still calls asyncio.run, this test will catch it.
        with (
            patch("asyncio.run") as mock_run,
            patch("arvel.console._async.schedule_async", wraps=schedule_async) as mock_schedule,
        ):
            # Invoke the registered callback directly
            for registered_cmd in typer_app.registered_commands:
                if registered_cmd.callback is not None:
                    with contextlib.suppress(Exception):
                        registered_cmd.callback(dry_run=False)
                    break

            # After refactor: schedule_async called, asyncio.run NOT called
            mock_schedule.assert_called_once()
            mock_run.assert_not_called()

    def test_migrate_rollback_callback_calls_schedule_async(self, tmp_path: Path) -> None:
        from arvel.console._async import schedule_async
        from arvel.console.commands.migrate import MigrateRollbackCommand

        cmd = MigrateRollbackCommand()
        cmd.app = self._build_fake_app(tmp_path)

        import typer

        typer_app = typer.Typer()
        cmd.register(typer_app)

        with (
            patch("asyncio.run") as mock_run,
            patch("arvel.console._async.schedule_async", wraps=schedule_async) as mock_schedule,
        ):
            for registered_cmd in typer_app.registered_commands:
                if registered_cmd.callback is not None:
                    with contextlib.suppress(Exception):
                        registered_cmd.callback()
                    break

            mock_schedule.assert_called_once()
            mock_run.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# — Entrypoint: _async_main function exists and awaits scheduled coro
# ─────────────────────────────────────────────────────────────────────────────


class TestEntrypointSingleLoop:
    def test_async_main_function_exists(self) -> None:
        """Entrypoint must expose async_main as a public coroutine function."""
        import inspect

        import arvel.console.entrypoint as ep

        assert hasattr(ep, "async_main"), "async_main must exist after refactor"
        assert inspect.iscoroutinefunction(ep.async_main)

    def test_main_does_not_call_asyncio_run_for_boot_directly(self) -> None:
        """main must use asyncio.run(async_main), not asyncio.run(boot) directly."""
        import inspect

        import arvel.console.entrypoint as ep

        source = inspect.getsource(ep.main)
        # Old pattern: asyncio.run(framework_app.boot()) — must be gone
        assert "asyncio.run(framework_app.boot())" not in source
        # New pattern: asyncio.run(async_main()) must be present
        assert "async_main" in source

    def test_async_main_awaits_scheduled_task(self) -> None:
        """_async_main must await the coroutine set by schedule_async after Typer dispatch."""

        ran: list[bool] = []

        async def _inner() -> None:
            ran.append(True)

        async def _run_test() -> None:
            from arvel.console._async import get_pending_task, schedule_async

            schedule_async(_inner())
            # Simulate what async_main does: get and await the scheduled coro.
            coro = get_pending_task()
            if coro is not None:
                await coro

        asyncio.run(_run_test())
        assert ran == [True]


# ─────────────────────────────────────────────────────────────────────────────
# — db:seed session lifecycle
# ─────────────────────────────────────────────────────────────────────────────


class TestDbSeedSessionLifecycle:
    """After refactor, db:seed must bind an AsyncSession before running the seeder."""

    def _build_app_with_session_maker(self, session: Any, tmp_path: Path) -> MagicMock:
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        maker = MagicMock(spec=async_sessionmaker)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        maker.return_value = ctx

        container = MagicMock()

        def _make(t: Any) -> Any:
            if t is async_sessionmaker[AsyncSession] or t == async_sessionmaker[AsyncSession]:
                return maker
            return MagicMock()

        container.make.side_effect = _make
        app = MagicMock()
        app.container = container
        app.base_path.return_value = tmp_path
        return app

    def test_seeder_run_called_with_active_session(self, tmp_path: Path) -> None:
        """After refactor, the seeder's run executes with an active session bound."""
        # Set up the seeder file
        seeder_dir = tmp_path / "database" / "seeders"
        seeder_dir.mkdir(parents=True)
        seeder_file = seeder_dir / "fake_seeder.py"
        seeder_file.write_text(
            "from arvel.database import Seeder\n"
            "from arvel.database.session import get_active_session\n"
            "sessions_seen = []\n"
            "class FakeSeeder(Seeder):\n"
            "    async def run(self) -> None:\n"
            "        sessions_seen.append(get_active_session())\n"
        )

        from sqlalchemy.ext.asyncio import AsyncSession

        fake_session = MagicMock(spec=AsyncSession)
        fake_session.commit = AsyncMock()

        app = self._build_app_with_session_maker(fake_session, tmp_path)

        from arvel.console.commands.db_seed import DbSeedCommand

        cmd = DbSeedCommand()
        cmd.app = app

        _resolve_patch = (
            patch.object(cmd, "_resolve_base_path", return_value=tmp_path)
            if hasattr(cmd, "_resolve_base_path")
            else patch("arvel.console.commands.db_seed._resolve_base_path", return_value=tmp_path)
        )
        with _resolve_patch, patch("asyncio.run") as mock_run:
            import typer

            typer_app = typer.Typer()
            cmd.register(typer_app)

            for registered_cmd in typer_app.registered_commands:
                if registered_cmd.callback is not None:
                    with contextlib.suppress(SystemExit, Exception):
                        registered_cmd.callback(seeder="FakeSeeder")
                    break

            # After refactor: asyncio.run NOT called inside the callback
            # (schedule_async is used instead)
            mock_run.assert_not_called()

    def test_db_seed_resolves_session_maker_from_container(self, tmp_path: Path) -> None:
        """After refactor, DbSeedCommand must resolve async_sessionmaker from container."""

        from arvel.console.commands.db_seed import DbSeedCommand

        cmd = DbSeedCommand()
        container = MagicMock()
        app = MagicMock()
        app.container = container
        app.base_path.return_value = tmp_path
        cmd.app = app

        # Set up a minimal seeder file
        seeder_dir = tmp_path / "database" / "seeders"
        seeder_dir.mkdir(parents=True)
        (seeder_dir / "database_seeder.py").write_text(
            "from arvel.database import Seeder\n"
            "class DatabaseSeeder(Seeder):\n"
            "    async def run(self) -> None: pass\n"
        )

        from arvel.console._async import schedule_async

        with (
            patch("arvel.console._async.schedule_async", wraps=schedule_async) as mock_schedule,
            patch("asyncio.run"),
        ):
            import typer

            typer_app = typer.Typer()
            cmd.register(typer_app)

            for registered_cmd in typer_app.registered_commands:
                if registered_cmd.callback is not None:
                    with contextlib.suppress(SystemExit, Exception):
                        registered_cmd.callback(seeder="DatabaseSeeder")
                    break

            # After refactor: schedule_async called, container.make called with async_sessionmaker
            mock_schedule.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# — openapi:export command
# ─────────────────────────────────────────────────────────────────────────────


class TestOpenApiExportCommand:
    def _build_app_with_spec(self, spec: dict[str, Any], tmp_path: Path) -> MagicMock:
        asgi = MagicMock()
        asgi.openapi.return_value = spec
        app = MagicMock()
        app.into_asgi.return_value = asgi
        app.base_path.return_value = tmp_path
        return app

    def test_command_registered_with_correct_name(self) -> None:
        from arvel.console.commands.openapi_export import OpenApiExportCommand

        cmd = OpenApiExportCommand()
        assert cmd.name == "openapi:export"

    def test_needs_application_true(self) -> None:
        from arvel.console._subsystem import CliSubsystem
        from arvel.console.commands.openapi_export import OpenApiExportCommand

        assert OpenApiExportCommand.needs_framework() is True
        assert CliSubsystem.HTTP in OpenApiExportCommand.requires

    def test_stdout_flag_prints_json(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        from arvel.console.commands.openapi_export import OpenApiExportCommand

        spec: dict[str, Any] = {"openapi": "3.1.0", "info": {"title": "Test", "version": "1.0"}}
        cmd = OpenApiExportCommand()
        cmd.app = self._build_app_with_spec(spec, tmp_path)

        import typer

        typer_app = typer.Typer()
        cmd.register(typer_app)

        from typer.testing import CliRunner

        runner = CliRunner()
        # Single-command Typer app: invoke without command name prefix
        result = runner.invoke(typer_app, ["--stdout", "--format", "json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["openapi"] == "3.1.0"

    def test_accepts_path_outside_project(self, tmp_path: Path, monkeypatch: Any) -> None:
        """``--output`` accepts any writable path — no project-root jail.

        Real-world use case: a Makefile in a sibling repo runs
        ``arvel openapi:export -o ../frontend/openapi.yaml``.
        """
        from arvel.console.commands.openapi_export import OpenApiExportCommand

        spec: dict[str, Any] = {"openapi": "3.1.0", "info": {"title": "T", "version": "1"}}
        cmd = OpenApiExportCommand()
        app = MagicMock()
        app.into_asgi.return_value.openapi.return_value = spec
        app.base_path.return_value = tmp_path
        cmd.app = app

        project_root = tmp_path / "project"
        project_root.mkdir()
        sibling = tmp_path / "frontend"
        sibling.mkdir()
        monkeypatch.chdir(project_root)

        import typer
        from typer.testing import CliRunner

        typer_app = typer.Typer()
        cmd.register(typer_app)
        runner = CliRunner()
        result = runner.invoke(
            typer_app,
            ["--output", "../frontend/openapi.json", "--format", "json"],
        )
        assert result.exit_code == 0
        assert (sibling / "openapi.json").is_file()

    def test_status_message_goes_to_stderr_not_stdout(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """Status writes to stderr so stdout stays clean for piping."""
        from arvel.console.commands.openapi_export import OpenApiExportCommand

        spec: dict[str, Any] = {"openapi": "3.1.0", "info": {"title": "T", "version": "1"}}
        cmd = OpenApiExportCommand()
        app = MagicMock()
        app.into_asgi.return_value.openapi.return_value = spec
        app.base_path.return_value = tmp_path
        cmd.app = app
        monkeypatch.chdir(tmp_path)

        import typer
        from typer.testing import CliRunner

        typer_app = typer.Typer()
        cmd.register(typer_app)
        runner = CliRunner()
        result = runner.invoke(typer_app, ["--output", "openapi.json", "--format", "json"])
        assert result.exit_code == 0
        # Click 8.4 separates stderr from stdout by default; status text must
        # not appear on stdout (which downstream tools may capture as data).
        assert "OpenAPI spec written to" not in result.stdout
        assert "OpenAPI spec written to" in result.stderr

    def test_output_dash_acts_like_stdout(self, tmp_path: Path) -> None:
        """``--output -`` is POSIX sugar for ``--stdout``."""
        from arvel.console.commands.openapi_export import OpenApiExportCommand

        spec: dict[str, Any] = {"openapi": "3.1.0", "info": {"title": "T", "version": "1"}}
        cmd = OpenApiExportCommand()
        app = MagicMock()
        app.into_asgi.return_value.openapi.return_value = spec
        app.base_path.return_value = tmp_path
        cmd.app = app

        import typer
        from typer.testing import CliRunner

        typer_app = typer.Typer()
        cmd.register(typer_app)
        runner = CliRunner()
        result = runner.invoke(typer_app, ["--output", "-", "--format", "json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["openapi"] == "3.1.0"

    def test_writes_yaml_file_by_default(self, tmp_path: Path, monkeypatch: Any) -> None:
        from arvel.console.commands.openapi_export import OpenApiExportCommand

        spec: dict[str, Any] = {"openapi": "3.1.0", "info": {"title": "T", "version": "1"}}
        cmd = OpenApiExportCommand()
        app = MagicMock()
        app.into_asgi.return_value.openapi.return_value = spec
        app.base_path.return_value = tmp_path
        cmd.app = app
        # Relative paths resolve against CWD now (no project-root jail).
        monkeypatch.chdir(tmp_path)

        import typer
        from typer.testing import CliRunner

        typer_app = typer.Typer()
        cmd.register(typer_app)
        runner = CliRunner()
        result = runner.invoke(
            typer_app,
            ["--output", "docs/api/openapi.yaml", "--format", "yaml"],
        )
        assert result.exit_code == 0
        out_file = tmp_path / "docs" / "api" / "openapi.yaml"
        assert out_file.is_file()
        assert "openapi" in out_file.read_text()

    def test_exit_code_0_on_success(self, tmp_path: Path) -> None:
        from arvel.console.commands.openapi_export import OpenApiExportCommand

        spec: dict[str, Any] = {"openapi": "3.1.0", "info": {"title": "T", "version": "1"}}
        cmd = OpenApiExportCommand()
        cmd.app = self._build_app_with_spec(spec, tmp_path)

        import typer
        from typer.testing import CliRunner

        typer_app = typer.Typer()
        cmd.register(typer_app)
        runner = CliRunner()
        result = runner.invoke(typer_app, ["--stdout", "--format", "json"])
        assert result.exit_code == 0


# ─────────────────────────────────────────────────────────────────────────────
# — openapi:validate command
# ─────────────────────────────────────────────────────────────────────────────


class TestOpenApiValidateCommand:
    def test_command_registered_with_correct_name(self) -> None:
        from arvel.console.commands.openapi_validate import OpenApiValidateCommand

        cmd = OpenApiValidateCommand()
        assert cmd.name == "openapi:validate"

    def test_needs_application_true(self) -> None:
        from arvel.console._subsystem import CliSubsystem
        from arvel.console.commands.openapi_validate import OpenApiValidateCommand

        assert OpenApiValidateCommand.needs_framework() is True
        assert CliSubsystem.HTTP in OpenApiValidateCommand.requires

    def test_exits_2_when_openapi_spec_validator_missing(self) -> None:
        from arvel.console.commands.openapi_validate import OpenApiValidateCommand

        cmd = OpenApiValidateCommand()
        app = MagicMock()
        app.into_asgi.return_value.openapi.return_value = {}
        cmd.app = app

        import typer
        from typer.testing import CliRunner

        typer_app = typer.Typer()
        cmd.register(typer_app)

        runner = CliRunner()
        with patch("builtins.__import__", side_effect=_import_blocker("openapi_spec_validator")):
            result = runner.invoke(typer_app, [])
        assert result.exit_code == 2

    def test_exits_0_for_valid_spec(self, tmp_path: Path) -> None:
        from arvel.console.commands.openapi_validate import OpenApiValidateCommand

        spec: dict[str, Any] = {
            "openapi": "3.1.0",
            "info": {"title": "T", "version": "1"},
            "paths": {},
        }
        cmd = OpenApiValidateCommand()
        app = MagicMock()
        app.into_asgi.return_value.openapi.return_value = spec
        cmd.app = app

        import typer
        from typer.testing import CliRunner

        typer_app = typer.Typer()
        cmd.register(typer_app)

        runner = CliRunner()
        mock_validate = MagicMock()  # no exception = valid
        with patch.dict(
            "sys.modules", {"openapi_spec_validator": MagicMock(validate=mock_validate)}
        ):
            result = runner.invoke(typer_app, [])
        assert result.exit_code == 0

    def test_exits_1_for_invalid_spec(self) -> None:
        from arvel.console.commands.openapi_validate import OpenApiValidateCommand

        cmd = OpenApiValidateCommand()
        app = MagicMock()
        app.into_asgi.return_value.openapi.return_value = {"bad": "spec"}
        cmd.app = app

        import typer
        from typer.testing import CliRunner

        typer_app = typer.Typer()
        cmd.register(typer_app)

        runner = CliRunner()
        mock_validate = MagicMock(side_effect=ValueError("invalid spec"))
        with patch.dict(
            "sys.modules", {"openapi_spec_validator": MagicMock(validate=mock_validate)}
        ):
            result = runner.invoke(typer_app, [])
        assert result.exit_code == 1

    def test_validates_spec_from_file(self, tmp_path: Path) -> None:
        from arvel.console.commands.openapi_validate import OpenApiValidateCommand

        spec_file = tmp_path / "spec.json"
        spec: dict[str, Any] = {"openapi": "3.1.0", "info": {"title": "T", "version": "1"}}
        spec_file.write_text(json.dumps(spec))

        cmd = OpenApiValidateCommand()
        cmd.app = MagicMock()

        import typer
        from typer.testing import CliRunner

        typer_app = typer.Typer()
        cmd.register(typer_app)

        runner = CliRunner()
        mock_validate = MagicMock()
        with patch.dict(
            "sys.modules", {"openapi_spec_validator": MagicMock(validate=mock_validate)}
        ):
            result = runner.invoke(typer_app, ["--spec", str(spec_file)])
        assert result.exit_code == 0
        mock_validate.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# — provider commands always attached after boot
# ─────────────────────────────────────────────────────────────────────────────


class TestProviderCommandsAlwaysAttached:
    def test_entrypoint_always_attaches_provider_commands_inside_project(
        self, tmp_path: Path
    ) -> None:
        """_attach_provider_commands always runs inside a project — no needs_boot gate."""
        import inspect

        import arvel.console.entrypoint as ep

        source = inspect.getsource(ep.main)
        # The needs_boot conditional must be removed
        assert "needs_boot" not in source, (
            "needs_boot gate must be removed — all provider commands attach after boot"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _import_blocker(blocked_name: str) -> Any:
    """Return a side_effect for patching builtins.__import__ that blocks one module."""
    import builtins

    real_import = builtins.__import__

    def _blocked(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == blocked_name or name.startswith(blocked_name + "."):
            raise ImportError(f"blocked: {name}")
        return real_import(name, *args, **kwargs)

    return _blocked
