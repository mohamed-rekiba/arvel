"""AuditServiceProvider — wires arvel-audit into an Arvel app.

Binds ``AuditConfig``, registers ``audit:install``, publishes the migration, and
re-asserts observer wiring for every ``Auditable`` model. ``Auditable`` already
wires its own hooks at class-definition time, so ``boot()`` is idempotent — it
exists so registration order with ``DatabaseServiceProvider`` stays explicit.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from arvel.providers.service_provider import ServiceProvider

from arvel_audit.auditable import wire_all_auditable
from arvel_audit.commands import AuditInstallCommand
from arvel_audit.config import AuditConfig

if TYPE_CHECKING:
    from arvel.console import Command


class AuditServiceProvider(ServiceProvider):
    """Boot arvel-audit inside an Arvel application."""

    def register(self) -> None:
        self.container.instance(AuditConfig, AuditConfig())

    async def boot(self) -> None:
        from arvel_audit import migrations as audit_migrations  # noqa: PLC0415

        stubs = Path(audit_migrations.__file__).parent
        self.publishes(
            {
                stubs / "create_audit_entries_table.py": "database/migrations",
                stubs / "create_activity_entries_table.py": "database/migrations",
            },
            tag="arvel-audit",
            is_migrations=True,
        )
        wire_all_auditable()

    def commands(self) -> list[type[Command] | Command]:
        return [AuditInstallCommand]


__all__ = ["AuditServiceProvider"]
