"""Tests for arvel make:* generator commands."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from typer.testing import CliRunner

if TYPE_CHECKING:
    import pytest

from arvel.cli.app import app

runner = CliRunner()


class TestMakeModule:
    def test_make_module_creates_structure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os

        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

        result = runner.invoke(app, ["make", "module", "users"])
        assert result.exit_code == 0
        assert "Module created" in result.output

        module_dir = tmp_path / "app" / "modules" / "users"
        assert module_dir.exists()
        assert (module_dir / "provider.py").exists()
        assert (module_dir / "routes.py").exists()
        assert (module_dir / "controllers" / "__init__.py").exists()
        assert (module_dir / "models" / "__init__.py").exists()
        assert (module_dir / "services" / "__init__.py").exists()
        assert (module_dir / "repositories" / "__init__.py").exists()

    def test_make_module_already_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os

        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

        module_dir = tmp_path / "app" / "modules" / "users"
        module_dir.mkdir(parents=True)

        result = runner.invoke(app, ["make", "module", "users"])
        assert result.exit_code == 1
        assert "already exists" in result.output


class TestMakeModel:
    def test_make_model(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

        result = runner.invoke(app, ["make", "model", "User", "--module", "users"])
        assert result.exit_code == 0
        assert "Model created" in result.output

        filepath = tmp_path / "app" / "modules" / "users" / "models" / "user.py"
        assert filepath.exists()
        content = filepath.read_text()
        assert "class User(ArvelModel)" in content
        assert '__tablename__ = "users"' in content


class TestMakeController:
    def test_make_controller(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

        result = runner.invoke(app, ["make", "controller", "UserController", "--module", "users"])
        assert result.exit_code == 0
        assert "Controller created" in result.output

        filepath = tmp_path / "app" / "modules" / "users" / "controllers" / "user_controller.py"
        assert filepath.exists()
        content = filepath.read_text()
        assert "class UserController" in content
        assert "UserService" in content


class TestMakeService:
    def test_make_service(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

        result = runner.invoke(app, ["make", "service", "UserService", "--module", "users"])
        assert result.exit_code == 0
        assert "Service created" in result.output

        filepath = tmp_path / "app" / "modules" / "users" / "services" / "user_service.py"
        assert filepath.exists()
        content = filepath.read_text()
        assert "class UserService" in content
        assert "UserRepository" in content


class TestMakeRepository:
    def test_make_repository(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

        result = runner.invoke(app, ["make", "repository", "UserRepository", "--module", "users"])
        assert result.exit_code == 0
        assert "Repository created" in result.output

        filepath = tmp_path / "app" / "modules" / "users" / "repositories" / "user_repository.py"
        assert filepath.exists()
        content = filepath.read_text()
        assert "class UserRepository(Repository[User])" in content


class TestMakeJob:
    def test_make_job(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

        result = runner.invoke(app, ["make", "job", "SendWelcomeEmail", "--module", "users"])
        assert result.exit_code == 0
        assert "Job created" in result.output

        filepath = tmp_path / "app" / "modules" / "users" / "jobs" / "send_welcome_email.py"
        assert filepath.exists()
        content = filepath.read_text()
        assert "class SendWelcomeEmail(Job)" in content


class TestMakeEvent:
    def test_make_event(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

        result = runner.invoke(app, ["make", "event", "UserRegistered", "--module", "users"])
        assert result.exit_code == 0
        assert "Event created" in result.output

        filepath = tmp_path / "app" / "modules" / "users" / "events" / "user_registered.py"
        assert filepath.exists()
        content = filepath.read_text()
        assert "class UserRegistered(Event)" in content


class TestMakeListener:
    def test_make_listener(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

        result = runner.invoke(
            app, ["make", "listener", "SendWelcomeEmailListener", "--module", "users"]
        )
        assert result.exit_code == 0
        assert "Listener created" in result.output

        filepath = (
            tmp_path / "app" / "modules" / "users" / "listeners" / "send_welcome_email_listener.py"
        )
        assert filepath.exists()
        content = filepath.read_text()
        assert "class SendWelcomeEmailListener(Listener)" in content


class TestMakePolicy:
    def test_make_policy(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

        result = runner.invoke(app, ["make", "policy", "UserPolicy", "--module", "users"])
        assert result.exit_code == 0
        assert "Policy created" in result.output

        filepath = tmp_path / "app" / "modules" / "users" / "policies" / "user_policy.py"
        assert filepath.exists()
        content = filepath.read_text()
        assert "class UserPolicy" in content


class TestMakeMail:
    def test_make_mail(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

        result = runner.invoke(app, ["make", "mail", "WelcomeMail", "--module", "users"])
        assert result.exit_code == 0
        assert "Mail created" in result.output

        filepath = tmp_path / "app" / "modules" / "users" / "mail" / "welcome_mail.py"
        assert filepath.exists()
        content = filepath.read_text()
        assert "class WelcomeMail" in content


class TestMakeSeeder:
    def test_make_seeder(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

        result = runner.invoke(app, ["make", "seeder", "UserSeeder"])
        assert result.exit_code == 0
        assert "Seeder created" in result.output

        filepath = tmp_path / "database" / "seeders" / "user_seeder.py"
        assert filepath.exists()
        content = filepath.read_text()
        assert "class UserSeeder(Seeder)" in content
        assert "async def run" in content


class TestMakeMigration:
    def test_make_migration_help(self) -> None:
        result = runner.invoke(app, ["make", "migration", "--help"])
        assert result.exit_code == 0
        assert "NAME" in result.output or "name" in result.output.lower()


class TestTemplateOverride:
    """Story 3: User stubs/ overrides built-in templates during make."""

    def test_custom_stub_overrides_builtin(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os

        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

        stubs_dir = tmp_path / "stubs"
        stubs_dir.mkdir()
        (stubs_dir / "model.py.j2").write_text(
            '"""CUSTOM TEMPLATE"""\n'
            "class {{ class_name }}:\n"
            '    __tablename__ = "{{ table_name }}"\n'
        )

        result = runner.invoke(app, ["make", "model", "Order", "--module", "shop"])
        assert result.exit_code == 0

        filepath = tmp_path / "app" / "modules" / "shop" / "models" / "order.py"
        assert filepath.exists()
        content = filepath.read_text()
        assert "CUSTOM TEMPLATE" in content
        assert "class Order" in content
