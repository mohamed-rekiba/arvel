"""``arvel auth:install`` / ``arvel vendor:publish`` integration tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from arvel.application import Application
from arvel.auth.commands.install import AuthInstallCommand
from arvel.auth.config import AuthConfig, JwtConfig
from arvel.auth.provider import AuthServiceProvider
from arvel.support.publishing import PublishRegistry


async def _booted_app(tmp_path: Path) -> tuple[Application, AuthServiceProvider]:
    """Create a bare Application with AuthServiceProvider booted and base_path set."""
    app = Application()
    registry = PublishRegistry()
    app.container.instance(PublishRegistry, registry)
    config = AuthConfig(default="web", jwt=JwtConfig(secret="s" * 32))
    app.container.instance(AuthConfig, config)
    provider = AuthServiceProvider(app)
    provider.register()
    with patch.object(app, "base_path", return_value=tmp_path):
        await provider.boot()
    app.use_base_path(tmp_path)
    return app, provider


@pytest.mark.asyncio
async def test_arvel_auth_install_command_publishes_all_tags(tmp_path: Path) -> None:
    """`arvel auth:install` writes config + routes + views + migrations."""
    app, _ = await _booted_app(tmp_path)

    cmd = AuthInstallCommand()
    cmd.app = app
    code = cmd.install(force=False)

    assert code == 0
    # Config and routes stubs should be present.
    assert (tmp_path / "config" / "auth.py").exists()
    assert (tmp_path / "routes" / "auth.py").exists()
    # 5 view templates should be present.
    assert (tmp_path / "templates" / "layouts" / "base.html.j2").exists()
    assert (tmp_path / "templates" / "auth" / "emails" / "verify_email.html.j2").exists()
    assert (tmp_path / "templates" / "auth" / "emails" / "verify_email.txt.j2").exists()
    assert (tmp_path / "templates" / "auth" / "emails" / "password_reset.html.j2").exists()
    assert (tmp_path / "templates" / "auth" / "emails" / "password_reset.txt.j2").exists()
    # At least one migration file in database/migrations/.
    migration_dir = tmp_path / "database" / "migrations"
    assert migration_dir.exists()
    migration_files = list(migration_dir.iterdir())
    assert len(migration_files) >= 1


@pytest.mark.asyncio
async def test_arvel_auth_install_idempotent_skip_existing(tmp_path: Path) -> None:
    """re-running skips files that already exist (no overwrite without --force)."""
    app, _ = await _booted_app(tmp_path)

    cmd = AuthInstallCommand()
    cmd.app = app

    # First run — publish everything.
    code1 = cmd.install(force=False)
    assert code1 == 0

    config_file = tmp_path / "config" / "auth.py"
    assert config_file.exists()
    original_mtime = config_file.stat().st_mtime

    # Second run — should skip existing files.
    code2 = cmd.install(force=False)
    assert code2 == 0
    assert config_file.stat().st_mtime == original_mtime


@pytest.mark.asyncio
async def test_arvel_auth_install_force_overwrites(tmp_path: Path) -> None:
    """`--force` overwrites existing files."""
    app, _ = await _booted_app(tmp_path)

    cmd = AuthInstallCommand()
    cmd.app = app

    # First run.
    cmd.install(force=False)
    config_file = tmp_path / "config" / "auth.py"
    config_file.write_text("# custom content")

    # Force overwrite.
    cmd.install(force=True)
    assert "# custom content" not in config_file.read_text()


@pytest.mark.asyncio
async def test_publish_arvel_auth_views_lays_down_5_files(tmp_path: Path) -> None:
    """layouts/base.html.j2 + verify_email.{html,txt}.j2 + password_reset.{html,txt}.j2"""
    app, _ = await _booted_app(tmp_path)

    registry = app.container.make(PublishRegistry)
    view_items = [i for i in registry.all() if i.tag == "arvel-auth-views"]
    assert len(view_items) == 5, f"Expected 5 view publishables, got {len(view_items)}"

    published_names = {item.source.name for item in view_items}
    assert "base.html.j2" in published_names
    assert "verify_email.html.j2" in published_names
    assert "verify_email.txt.j2" in published_names
    assert "password_reset.html.j2" in published_names
    assert "password_reset.txt.j2" in published_names


@pytest.mark.asyncio
async def test_publish_arvel_auth_migrations_timestamps_filenames(tmp_path: Path) -> None:
    """Migrations land with YYYY_MM_DD_HHMMSS_ prefix in chronological order."""
    import re

    app, _ = await _booted_app(tmp_path)

    cmd = AuthInstallCommand()
    cmd.app = app
    cmd.install(force=False)

    migration_dir = tmp_path / "database" / "migrations"
    migration_files = sorted(migration_dir.iterdir())
    assert len(migration_files) >= 1

    pattern = re.compile(r"^\d{4}_\d{2}_\d{2}_\d{6}_")
    for f in migration_files:
        assert pattern.match(f.name), f"Migration file {f.name!r} lacks timestamp prefix"


@pytest.mark.asyncio
async def test_publish_arvel_auth_config_creates_config_auth_py(tmp_path: Path) -> None:
    """User can edit the published file without affecting the framework."""
    app, _ = await _booted_app(tmp_path)

    cmd = AuthInstallCommand()
    cmd.app = app
    cmd.install(force=False)

    config_file = tmp_path / "config" / "auth.py"
    assert config_file.exists()

    # Verify it's a copy — modifying it doesn't affect the source stub.
    registry = app.container.make(PublishRegistry)
    config_item = next(i for i in registry.all() if i.tag == "arvel-auth-config")
    original_content = config_item.source.read_text()

    config_file.write_text("# modified by user")
    assert config_item.source.read_text() == original_content
