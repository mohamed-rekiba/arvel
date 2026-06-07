"""audit:install command wiring and migration shape."""

from __future__ import annotations

import inspect

from arvel_audit import AuditInstallCommand
from arvel_audit.migrations import (
    create_activity_entries_table as activity_migration,
)
from arvel_audit.migrations import (
    create_audit_entries_table as audit_migration,
)
from arvel_audit.provider import AuditServiceProvider


def test_provider_registers_install_command() -> None:
    provider = AuditServiceProvider.__new__(AuditServiceProvider)
    assert AuditInstallCommand in provider.commands()


def test_install_command_metadata() -> None:
    from arvel.console._subsystem import CliSubsystem

    assert AuditInstallCommand.name == "audit:install"
    assert AuditInstallCommand.needs_framework() is True
    assert CliSubsystem.USER_PROVIDERS in AuditInstallCommand.requires


def test_both_migrations_define_up_and_down() -> None:
    for migration in (audit_migration, activity_migration):
        assert inspect.iscoroutinefunction(migration.up)
        assert inspect.iscoroutinefunction(migration.down)


def test_install_without_application_exits_nonzero() -> None:
    command = AuditInstallCommand()
    assert command.install(force=False) == 2
