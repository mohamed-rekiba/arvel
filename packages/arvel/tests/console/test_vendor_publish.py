"""Tests for the vendor:publish command + ServiceProvider.publishes() API."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from arvel import Application, ServiceProvider
from arvel.console import Application as ConsoleApplication
from arvel.console.commands.config_commands import ConfigPublishCommand
from arvel.console.commands.vendor_publish import VendorPublishCommand
from arvel.support.publishing import (
    Publishable,
    PublishRegistry,
    rewrite_migration_filename,
)
from typer.testing import CliRunner

runner = CliRunner()


# ─── PublishRegistry primitive ───────────────────────────────────────────────


def test_registry_records_items_in_order() -> None:
    reg = PublishRegistry()
    a = Publishable(
        source=Path("/pkg/a.py"),
        destination=Path("/app/a.py"),
        tag="t1",
        provider="some.Provider",
        is_migration=False,
    )
    b = Publishable(
        source=Path("/pkg/b.py"),
        destination=Path("/app/b.py"),
        tag="t2",
        provider="some.Provider",
        is_migration=False,
    )
    reg.add([a])
    reg.add([b])
    assert reg.all() == [a, b]


def test_registry_filters_by_tag_and_provider() -> None:
    reg = PublishRegistry()
    p1 = Publishable(
        source=Path("/x.py"),
        destination=Path("/y.py"),
        tag="auth",
        provider="arvel.auth.AuthServiceProvider",
        is_migration=True,
    )
    p2 = Publishable(
        source=Path("/x2.py"),
        destination=Path("/y2.py"),
        tag="cache",
        provider="arvel.providers.CacheServiceProvider",
        is_migration=True,
    )
    reg.add([p1, p2])
    assert reg.by_tag("auth") == [p1]
    # bare class name lookup also works (Laravel parity)
    assert reg.by_provider("AuthServiceProvider") == [p1]
    assert reg.tags() == ["auth", "cache"]


# ─── filename rewrite ────────────────────────────────────────────────────────


def test_rewrite_migration_filename_strips_existing_timestamp() -> None:
    src = Path("packages/arvel/src/arvel/auth/migrations/create_users_table.py")
    fixed = datetime.datetime(2026, 5, 20, 12, 34, 56, tzinfo=datetime.UTC)
    out = rewrite_migration_filename(src, Path("/app/database/migrations"), now=fixed)
    assert out == Path("/app/database/migrations/2026_05_20_123456_create_users_table.py")


def test_rewrite_migration_filename_disambiguates_with_microseconds() -> None:
    src = Path("create_users_table.py")
    fixed = datetime.datetime(2026, 5, 20, 12, 34, 56, tzinfo=datetime.UTC)
    used: set[Path] = set()
    first = rewrite_migration_filename(src, Path("/d"), now=fixed, used=used)
    second = rewrite_migration_filename(src, Path("/d"), now=fixed, used=used)
    assert first != second


# ─── ServiceProvider.publishes() ─────────────────────────────────────────────


class _StubMigrationProvider(ServiceProvider):
    """Test provider that registers a single publishable migration."""

    stub_path: Path

    def register(self) -> None:
        pass

    async def boot(self) -> None:
        self.publishes(
            {self.stub_path: "database/migrations"},
            tag="stub",
            is_migrations=True,
        )


def _make_stub_provider(stub: Path) -> type[_StubMigrationProvider]:
    """Create a fresh provider class that points at ``stub``."""
    return type(
        "_TestProvider",
        (_StubMigrationProvider,),
        {"stub_path": stub},
    )


@pytest.mark.asyncio
async def test_publishes_records_into_app_registry(tmp_path: Path) -> None:
    stub = tmp_path / "create_things_table.py"
    stub.write_text("# migration body\n")
    provider_cls = _make_stub_provider(stub)
    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([provider_cls])
        .create()
    )
    await app.boot()

    reg: PublishRegistry = app.container.make(PublishRegistry)
    items = reg.all()
    assert len(items) == 1
    assert items[0].source == stub.resolve()
    assert items[0].destination == (tmp_path / "database" / "migrations").resolve()
    assert items[0].tag == "stub"
    assert items[0].is_migration is True


# ─── vendor:publish command ──────────────────────────────────────────────────


def _cli(app: Application) -> ConsoleApplication:
    cmd = VendorPublishCommand()
    cmd.app = app
    return ConsoleApplication([cmd])


def test_config_publish_command_is_registered() -> None:
    cli = ConsoleApplication([ConfigPublishCommand()])

    assert ConfigPublishCommand.name == "config:publish"
    assert cli.has_command("config:publish")


@pytest.mark.asyncio
async def test_vendor_publish_copies_stub_with_timestamp(tmp_path: Path) -> None:
    stub = tmp_path / "pkg" / "create_demo_table.py"
    stub.parent.mkdir(parents=True)
    stub.write_text("# DEMO STUB\n")

    provider_cls = _make_stub_provider(stub)
    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([provider_cls])
        .create()
    )
    await app.boot()

    cli = _cli(app)
    result = runner.invoke(cli.typer_app, ["vendor:publish", "--tag", "stub"])
    assert result.exit_code == 0, result.output

    published = list((tmp_path / "database" / "migrations").glob("*_create_demo_table.py"))
    assert len(published) == 1
    assert published[0].read_text() == "# DEMO STUB\n"


@pytest.mark.asyncio
async def test_vendor_publish_filters_by_provider(tmp_path: Path) -> None:
    stub = tmp_path / "pkg" / "create_alpha_table.py"
    stub.parent.mkdir(parents=True)
    stub.write_text("# ALPHA\n")

    provider_cls = _make_stub_provider(stub)
    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([provider_cls])
        .create()
    )
    await app.boot()

    cli = _cli(app)
    bare_name = provider_cls.__name__
    result = runner.invoke(cli.typer_app, ["vendor:publish", "--provider", bare_name])
    assert result.exit_code == 0, result.output
    assert list((tmp_path / "database" / "migrations").glob("*_create_alpha_table.py"))


@pytest.mark.asyncio
async def test_vendor_publish_skips_existing_unless_force(tmp_path: Path) -> None:
    stub = tmp_path / "pkg" / "create_beta_table.py"
    stub.parent.mkdir(parents=True)
    stub.write_text("# NEW\n")

    target_dir = tmp_path / "database" / "migrations"
    target_dir.mkdir(parents=True)
    existing = target_dir / "2020_01_01_000000_create_beta_table.py"
    existing.write_text("# OLD\n")

    provider_cls = _make_stub_provider(stub)
    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([provider_cls])
        .create()
    )
    await app.boot()

    cli = _cli(app)

    # Without --force, the new file is published with a fresh timestamp;
    # the existing one is left alone (different basenames, no collision).
    result = runner.invoke(cli.typer_app, ["vendor:publish", "--tag", "stub"])
    assert result.exit_code == 0
    assert existing.read_text() == "# OLD\n"
    new_files = [f for f in target_dir.glob("*_create_beta_table.py") if f != existing]
    assert len(new_files) == 1
    assert new_files[0].read_text() == "# NEW\n"


@pytest.mark.asyncio
async def test_vendor_publish_reports_nothing_to_publish(tmp_path: Path) -> None:
    stub = tmp_path / "pkg" / "create_zeta_table.py"
    stub.parent.mkdir(parents=True)
    stub.write_text("# Z\n")
    provider_cls = _make_stub_provider(stub)
    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([provider_cls])
        .create()
    )
    await app.boot()

    cli = _cli(app)
    result = runner.invoke(cli.typer_app, ["vendor:publish", "--tag", "nope"])
    assert result.exit_code == 0
    assert "Nothing to publish." in result.output


def test_vendor_publish_without_application_exits_two() -> None:
    cmd = VendorPublishCommand()
    # No bound Application — simulates running outside a project.
    cmd.app = None
    cli = ConsoleApplication([cmd])
    result = runner.invoke(cli.typer_app, ["vendor:publish"])
    assert result.exit_code == 2
    assert "requires a framework Application" in (result.output + (result.stderr or ""))


# ─── framework providers register their stubs ───────────────────────────────


@pytest.mark.asyncio
async def test_framework_providers_register_known_tags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sanity-check: each shipped provider registers under its expected tag."""
    from arvel.facades.bus import Bus as BusFacade
    from arvel.facades.cache import Cache as CacheFacade
    from arvel.facades.notification import Notification as NotificationFacade
    from arvel.facades.session import Session as SessionFacade
    from arvel.notifications.providers.notification_service_provider import (
        NotificationServiceProvider,
    )
    from arvel.providers.cache_provider import CacheServiceProvider
    from arvel.providers.session_provider import SessionServiceProvider
    from arvel.queue.providers.queue_service_provider import QueueServiceProvider

    # Booting each provider binds its global facade. Snapshot + restore
    # via monkeypatch so sibling tests asserting "facade unbound" don't
    # see leaked state from this test.
    monkeypatch.setattr(BusFacade, "manager", None)
    monkeypatch.setattr(CacheFacade, "manager", None)
    monkeypatch.setattr(SessionFacade, "_manager", None)
    monkeypatch.setattr(NotificationFacade, "_manager", None)

    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers(
            [
                CacheServiceProvider,
                SessionServiceProvider,
                QueueServiceProvider,
                NotificationServiceProvider,
            ]
        )
        .create()
    )
    await app.boot()

    reg: PublishRegistry = app.container.make(PublishRegistry)
    tags = reg.tags()
    assert "arvel-cache" in tags
    assert "arvel-session" in tags
    assert "arvel-queue" in tags
    assert "arvel-notifications" in tags

    queue_items = reg.by_tag("arvel-queue")
    queue_basenames = {item.source.name for item in queue_items}
    assert queue_basenames == {
        "create_jobs_table.py",
        "create_failed_jobs_table.py",
    }
