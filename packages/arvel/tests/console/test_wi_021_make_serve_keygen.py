"""make:migration, serve, key:generate command generators.
make:migration generates timestamp-prefixed Alembic-shaped file
 serve runs uvicorn against public.asgi:asgi with sensible defaults
 key:generate produces base64 random key; writes to .env or --show
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# — make:migration
# ─────────────────────────────────────────────────────────────────────────────


class TestMakeMigration:
    def test_creates_timestamped_file_in_database_migrations(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.console.commands.make_migration import MakeMigrationCommand

        monkeypatch.chdir(tmp_path)
        code = MakeMigrationCommand().make("CreateUsersTable")
        assert code == 0

        target_dir = tmp_path / "database" / "migrations"
        assert target_dir.is_dir()

        files = list(target_dir.iterdir())
        assert len(files) == 1
        name = files[0].name
        assert re.match(r"\d{4}_\d{2}_\d{2}_\d{6}.*_create_users_table\.py$", name) or re.match(
            r"\d{4}_\d{2}_\d{2}_\d{6}_create_users_table\.py$", name
        )

    def test_file_content_imports_blueprint_and_schema(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.console.commands.make_migration import MakeMigrationCommand

        monkeypatch.chdir(tmp_path)
        MakeMigrationCommand().make("AddTagsTable")

        files = list((tmp_path / "database" / "migrations").iterdir())
        content = files[0].read_text()
        assert "from arvel.database import" in content
        assert "Blueprint" in content
        assert "Schema" in content
        assert "async def up" in content
        assert "async def down" in content

    def test_rejects_path_traversal_in_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Security: name must not embed `..`, `/`, or other path-traversal chars."""
        from arvel.console.commands.make_migration import MakeMigrationCommand

        monkeypatch.chdir(tmp_path)
        code = MakeMigrationCommand().make("../../etc/passwd")
        captured = capsys.readouterr()
        assert code == 2
        assert "Migration name must match" in captured.err
        assert not list(tmp_path.glob("**/passwd*"))

    def test_rejects_docstring_breakout_in_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Security: name must not contain `\"\"\"` (docstring breakout → code injection)."""
        from arvel.console.commands.make_migration import MakeMigrationCommand

        monkeypatch.chdir(tmp_path)
        code = MakeMigrationCommand().make('Foo"""\nimport os; os.system("touch /tmp/pwn")\n"""')
        captured = capsys.readouterr()
        assert code == 2
        assert "Migration name must match" in captured.err

    def test_rejects_empty_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from arvel.console.commands.make_migration import MakeMigrationCommand

        monkeypatch.chdir(tmp_path)
        code = MakeMigrationCommand().make("")
        captured = capsys.readouterr()
        assert code == 2
        assert "must not be empty" in captured.err

    def test_back_to_back_invocations_do_not_collide(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If two invocations land in the same second, the second gets a unique suffix."""
        from arvel.console.commands.make_migration import MakeMigrationCommand

        monkeypatch.chdir(tmp_path)
        with patch("arvel.console.commands.make_migration.datetime") as mock_dt:
            mock_dt.datetime.now.return_value.strftime.side_effect = [
                "2026_05_19_120000",
                "2026_05_19_120000",
                "2026_05_19_120000_000123",
            ]
            mock_dt.UTC = MagicMock()
            MakeMigrationCommand().make("CreateA")
            MakeMigrationCommand().make("CreateB")

        files = sorted(p.name for p in (tmp_path / "database" / "migrations").iterdir())
        assert len(files) == 2
        assert files[0] != files[1]


# ─────────────────────────────────────────────────────────────────────────────
# — serve
# ─────────────────────────────────────────────────────────────────────────────


class TestServe:
    def test_serve_outside_project_exits_two(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from arvel.console import Context
        from arvel.console.commands.serve import ServeCommand

        monkeypatch.chdir(tmp_path)
        code = ServeCommand().handle(Context())
        captured = capsys.readouterr()
        assert code == 2
        assert "requires an Arvel project context" in captured.err

    def test_serve_calls_uvicorn_with_defaults_inside_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.console.commands.serve import ServeCommand

        (tmp_path / "bootstrap").mkdir()
        (tmp_path / "bootstrap" / "app.py").write_text("def create_application(): pass\n")
        monkeypatch.chdir(tmp_path)

        with patch("arvel.console.commands.serve.uvicorn.run") as mock_run:
            ServeCommand().serve(host="127.0.0.1", port=8000, reload=True)

        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0] == "public.asgi:asgi" or kwargs.get("app") == "public.asgi:asgi"
        assert kwargs.get("host") == "127.0.0.1"
        assert kwargs.get("port") == 8000
        assert kwargs.get("reload") is True


# ─────────────────────────────────────────────────────────────────────────────
# — key:generate
# ─────────────────────────────────────────────────────────────────────────────


class TestKeyGenerate:
    def test_show_prints_base64_key(self, capsys: pytest.CaptureFixture[str]) -> None:
        from arvel.console.commands.key_generate import KeyGenerateCommand

        code = KeyGenerateCommand().generate(show=True, force=False)
        out = capsys.readouterr().out
        assert code == 0
        assert "base64:" in out

    def test_writes_app_key_line_to_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.console.commands.key_generate import KeyGenerateCommand

        monkeypatch.chdir(tmp_path)
        env_file = tmp_path / ".env"
        env_file.write_text("APP_NAME=arvel\nAPP_KEY=\n")

        code = KeyGenerateCommand().generate(show=False, force=False)
        assert code == 0
        content = env_file.read_text()
        assert "APP_KEY=base64:" in content

    def test_refuses_overwrite_without_force(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from arvel.console.commands.key_generate import KeyGenerateCommand

        monkeypatch.chdir(tmp_path)
        env_file = tmp_path / ".env"
        env_file.write_text("APP_KEY=base64:already_present_42_chars_long_enough==\n")

        code = KeyGenerateCommand().generate(show=False, force=False)
        captured = capsys.readouterr()
        assert code == 2
        assert "--force" in captured.err
        assert env_file.read_text().startswith("APP_KEY=base64:already_present")

    def test_force_overwrites_existing_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.console.commands.key_generate import KeyGenerateCommand

        monkeypatch.chdir(tmp_path)
        env_file = tmp_path / ".env"
        env_file.write_text("APP_KEY=base64:old_key_value\n")

        code = KeyGenerateCommand().generate(show=False, force=True)
        assert code == 0
        content = env_file.read_text()
        assert "APP_KEY=base64:" in content
        assert "old_key_value" not in content

    def test_no_env_file_without_show_exits_two(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from arvel.console.commands.key_generate import KeyGenerateCommand

        monkeypatch.chdir(tmp_path)
        code = KeyGenerateCommand().generate(show=False, force=False)
        captured = capsys.readouterr()
        assert code == 2
        assert ".env" in captured.err

    def test_writes_app_key_when_line_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.console.commands.key_generate import KeyGenerateCommand

        monkeypatch.chdir(tmp_path)
        env_file = tmp_path / ".env"
        env_file.write_text("APP_NAME=arvel")

        code = KeyGenerateCommand().generate(show=False, force=False)
        assert code == 0
        content = env_file.read_text()
        assert "APP_KEY=base64:" in content
        assert "APP_NAME=arvel" in content

    def test_writes_app_key_to_empty_env_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.console.commands.key_generate import KeyGenerateCommand

        monkeypatch.chdir(tmp_path)
        env_file = tmp_path / ".env"
        env_file.write_text("")

        code = KeyGenerateCommand().generate(show=False, force=False)
        assert code == 0
        assert "APP_KEY=base64:" in env_file.read_text()

    def test_register_callback_runs_via_typer(self) -> None:
        import typer
        from arvel.console.commands.key_generate import KeyGenerateCommand
        from typer.testing import CliRunner

        app = typer.Typer()
        KeyGenerateCommand().register(app)
        runner = CliRunner()
        result = runner.invoke(app, ["--show"])
        assert result.exit_code == 0
        assert "base64:" in result.output


# ─────────────────────────────────────────────────────────────────────────────
# make:migration register() callback wired through Typer
# ─────────────────────────────────────────────────────────────────────────────


class TestMakeMigrationRegister:
    def test_register_callback_writes_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import typer
        from arvel.console.commands.make_migration import MakeMigrationCommand
        from typer.testing import CliRunner

        monkeypatch.chdir(tmp_path)
        app = typer.Typer()
        MakeMigrationCommand().register(app)
        runner = CliRunner()
        result = runner.invoke(app, ["CreateThings"])
        assert result.exit_code == 0
        assert (tmp_path / "database" / "migrations").is_dir()

    def test_register_callback_view_flag_writes_view_stub(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import typer
        from arvel.console.commands.make_migration import MakeMigrationCommand
        from typer.testing import CliRunner

        monkeypatch.chdir(tmp_path)
        app = typer.Typer()
        MakeMigrationCommand().register(app)
        runner = CliRunner()
        result = runner.invoke(app, ["--view", "CreateActiveUsersView"])
        assert result.exit_code == 0

        files = list((tmp_path / "database" / "migrations").iterdir())
        assert len(files) == 1
        content = files[0].read_text()
        assert "create_view" in content
        assert "drop_view_if_exists" in content
        assert "Blueprint" not in content


# ─── make:migration --view ( extension) ─────────────────────────────


class TestMakeMigrationView:
    def test_view_flag_generates_view_stub(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.console.commands.make_migration import MakeMigrationCommand

        monkeypatch.chdir(tmp_path)
        code = MakeMigrationCommand().make("CreateActiveUsersView", view=True)
        assert code == 0

        files = list((tmp_path / "database" / "migrations").iterdir())
        assert len(files) == 1
        content = files[0].read_text()
        assert "create_view" in content
        assert "drop_view_if_exists" in content

    def test_view_stub_derives_view_name_without_suffix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.console.commands.make_migration import MakeMigrationCommand

        monkeypatch.chdir(tmp_path)
        MakeMigrationCommand().make("CreateActiveUsersView", view=True)

        content = next((tmp_path / "database" / "migrations").iterdir()).read_text()
        # "CreateActiveUsersView" → view name "active_users" (no suffix, no pluralise)
        assert '"active_users"' in content

    def test_view_stub_omits_blueprint_and_id_type(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.console.commands.make_migration import MakeMigrationCommand

        monkeypatch.chdir(tmp_path)
        MakeMigrationCommand().make("CreateSummaryView", view=True)

        content = next((tmp_path / "database" / "migrations").iterdir()).read_text()
        assert "Blueprint" not in content
        assert "IdType" not in content

    def test_table_stub_still_works_without_view_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.console.commands.make_migration import MakeMigrationCommand

        monkeypatch.chdir(tmp_path)
        MakeMigrationCommand().make("CreateOrdersTable")

        content = next((tmp_path / "database" / "migrations").iterdir()).read_text()
        assert "Blueprint" in content
        assert "schema.create" in content
        assert "create_view" not in content


# ─── make:migration --extension ──────────────────────────────────────────────


class TestMakeMigrationExtension:
    def test_extension_flag_generates_extension_stub(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.console.commands.make_migration import MakeMigrationCommand

        monkeypatch.chdir(tmp_path)
        code = MakeMigrationCommand().make("InstallUuidOsspExtension", extension=True)
        assert code == 0

        content = next((tmp_path / "database" / "migrations").iterdir()).read_text()
        assert "install_extension" in content
        assert "uninstall_extension" in content

    def test_extension_stub_derives_extension_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.console.commands.make_migration import MakeMigrationCommand

        monkeypatch.chdir(tmp_path)
        MakeMigrationCommand().make("InstallUuidOsspExtension", extension=True)

        content = next((tmp_path / "database" / "migrations").iterdir()).read_text()
        # "InstallUuidOsspExtension" → "uuid-ossp"
        assert '"uuid-ossp"' in content

    def test_extension_stub_omits_blueprint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.console.commands.make_migration import MakeMigrationCommand

        monkeypatch.chdir(tmp_path)
        MakeMigrationCommand().make("InstallPgTrgmExtension", extension=True)

        content = next((tmp_path / "database" / "migrations").iterdir()).read_text()
        assert "Blueprint" not in content
        assert "IdType" not in content

    def test_view_and_extension_flags_are_mutually_exclusive(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from arvel.console.commands.make_migration import MakeMigrationCommand

        monkeypatch.chdir(tmp_path)
        code = MakeMigrationCommand().make("Foo", view=True, extension=True)
        captured = capsys.readouterr()
        assert code == 2
        assert "mutually exclusive" in captured.err

    def test_materialized_view_and_view_flags_are_mutually_exclusive(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from arvel.console.commands.make_migration import MakeMigrationCommand

        monkeypatch.chdir(tmp_path)
        code = MakeMigrationCommand().make("Foo", view=True, materialized_view=True)
        captured = capsys.readouterr()
        assert code == 2
        assert "mutually exclusive" in captured.err

    def test_register_callback_extension_flag_writes_extension_stub(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import typer
        from arvel.console.commands.make_migration import MakeMigrationCommand
        from typer.testing import CliRunner

        monkeypatch.chdir(tmp_path)
        app = typer.Typer()
        MakeMigrationCommand().register(app)
        runner = CliRunner()
        result = runner.invoke(app, ["InstallPgcryptoExtension", "--extension"])
        assert result.exit_code == 0

        content = next((tmp_path / "database" / "migrations").iterdir()).read_text()
        assert "install_extension" in content
        assert "uninstall_extension" in content


# ─── make:migration --materialized-view ──────────────────────────────────────


class TestMakeMigrationMaterializedView:
    def test_materialized_view_flag_generates_stub(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.console.commands.make_migration import MakeMigrationCommand

        monkeypatch.chdir(tmp_path)
        code = MakeMigrationCommand().make("CreateDailyStatsView", materialized_view=True)
        assert code == 0

        content = next((tmp_path / "database" / "migrations").iterdir()).read_text()
        assert "create_materialized_view" in content
        assert "drop_materialized_view_if_exists" in content
        assert "refresh_materialized_view" in content

    def test_materialized_view_stub_derives_view_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.console.commands.make_migration import MakeMigrationCommand

        monkeypatch.chdir(tmp_path)
        MakeMigrationCommand().make("CreateDailyStatsView", materialized_view=True)

        content = next((tmp_path / "database" / "migrations").iterdir()).read_text()
        assert '"daily_stats"' in content

    def test_materialized_view_stub_omits_blueprint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.console.commands.make_migration import MakeMigrationCommand

        monkeypatch.chdir(tmp_path)
        MakeMigrationCommand().make("CreateDailyStatsView", materialized_view=True)

        content = next((tmp_path / "database" / "migrations").iterdir()).read_text()
        assert "Blueprint" not in content
        assert "IdType" not in content

    def test_register_callback_materialized_view_flag_writes_stub(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import typer
        from arvel.console.commands.make_migration import MakeMigrationCommand
        from typer.testing import CliRunner

        monkeypatch.chdir(tmp_path)
        app = typer.Typer()
        MakeMigrationCommand().register(app)
        runner = CliRunner()
        result = runner.invoke(app, ["--materialized-view", "CreateDailyStatsView"])
        assert result.exit_code == 0

        files = list((tmp_path / "database" / "migrations").iterdir())
        assert len(files) == 1
        content = files[0].read_text()
        assert "create_materialized_view" in content
        assert "drop_materialized_view_if_exists" in content


# ─────────────────────────────────────────────────────────────────────────────
# serve register() and handle()
# ─────────────────────────────────────────────────────────────────────────────


class TestServeRegister:
    def test_serve_handle_returns_zero_inside_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.console import Context
        from arvel.console.commands.serve import ServeCommand

        (tmp_path / "bootstrap").mkdir()
        (tmp_path / "bootstrap" / "app.py").write_text(
            "def create_application(): return object()\n"
        )
        monkeypatch.chdir(tmp_path)
        assert ServeCommand().handle(Context()) == 0

    def test_register_callback_invokes_serve_inside_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import typer
        from arvel.console.commands.serve import ServeCommand
        from typer.testing import CliRunner

        (tmp_path / "bootstrap").mkdir()
        (tmp_path / "bootstrap" / "app.py").write_text(
            "def create_application(): return object()\n"
        )
        monkeypatch.chdir(tmp_path)

        app = typer.Typer()
        ServeCommand().register(app)
        runner = CliRunner()
        with patch("arvel.console.commands.serve.uvicorn.run") as mock_run:
            result = runner.invoke(app, [])
        assert result.exit_code == 0
        mock_run.assert_called_once()


class TestServeBypassesEventLoop:
    """`arvel serve` must run uvicorn OUTSIDE the entrypoint's asyncio.run.

    Regression for: uvicorn.run() calls asyncio.run() internally, which raises
    "asyncio.run() cannot be called from a running event loop" when the
    entrypoint has already wrapped the invocation in asyncio.run(async_main()).
    """

    def test_serve_command_owns_process(self) -> None:
        from arvel.console.commands.serve import ServeCommand

        assert ServeCommand.owns_process is True

    def test_main_runs_serve_without_entering_event_loop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.console import entrypoint

        (tmp_path / "bootstrap").mkdir()
        (tmp_path / "bootstrap" / "app.py").write_text(
            "def create_application(): return object()\n"
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("sys.argv", ["arvel", "serve"])

        with (
            patch("arvel.console.commands.serve.uvicorn.run") as mock_run,
            patch.object(entrypoint.asyncio, "run") as mock_asyncio_run,
        ):
            with pytest.raises(SystemExit) as exc:
                entrypoint.main()

        assert exc.value.code == 0
        mock_run.assert_called_once()
        # The whole point: serve must NOT be dispatched through asyncio.run.
        mock_asyncio_run.assert_not_called()
