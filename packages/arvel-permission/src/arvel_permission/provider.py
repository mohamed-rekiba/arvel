"""PermissionServiceProvider — wires arvel-permission into an Arvel app.

Binds:

- ``PermissionConfig`` singleton in the container.
- A `before` hook on the bound ``Gate`` that resolves abilities against
  ``user.has_permission_to(...)`` (see :mod:`arvel_permission.gate_integration`).

Also registers ``create_permission_tables`` as a publishable migration so
consumers can stamp it into ``database/migrations/`` with
``arvel vendor:publish --tag=arvel-permission``.
"""

from __future__ import annotations

from pathlib import Path

from arvel.auth.gate import Gate
from arvel.container.errors import BindingResolutionError
from arvel.providers.service_provider import ServiceProvider

from arvel_permission.config import PermissionConfig
from arvel_permission.gate_integration import register_permissions_with_gate
from arvel_permission.traits import apply_model_config, apply_wildcard_config


class PermissionServiceProvider(ServiceProvider):
    """Boot arvel-permission inside an Arvel application."""

    config: PermissionConfig = PermissionConfig()

    def register(self) -> None:
        self.container.instance(PermissionConfig, self.config)

    async def boot(self) -> None:
        from arvel_permission import migrations as permission_migrations  # noqa: PLC0415

        stub = Path(permission_migrations.__file__).parent / "create_permission_tables.py"
        self.publishes(
            {stub: "database/migrations"},
            tag="arvel-permission",
            is_migrations=True,
        )

        apply_wildcard_config(self.config)
        apply_model_config(self.config)

        try:
            gate = self.container.make(Gate)
        except BindingResolutionError:
            return
        register_permissions_with_gate(gate, guard=self.config.default_guard_name)
