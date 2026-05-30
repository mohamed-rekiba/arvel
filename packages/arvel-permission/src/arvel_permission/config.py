"""Permission configuration — guard defaults, table names, cache settings.

Mirrors Spatie's `config/permission.php` knobs as a Pydantic settings model.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from arvel_permission.models import Permission, Role


class PermissionConfig(BaseModel):
    """Tuneable knobs for arvel-permission.

    Override at app boot via the PermissionServiceProvider's `register()`:

        provider.config = PermissionConfig(default_guard_name="api")
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    role_model: type[Role] = Field(default=Role)
    permission_model: type[Permission] = Field(default=Permission)
    default_guard_name: str = Field(
        default="web",
        description="Guard name applied when none is supplied (mirrors Spatie's default).",
    )
    roles_table: str = Field(default="roles")
    permissions_table: str = Field(default="permissions")
    model_has_roles_table: str = Field(default="model_has_roles")
    model_has_permissions_table: str = Field(default="model_has_permissions")
    role_has_permissions_table: str = Field(default="role_has_permissions")
    cache_enabled: bool = Field(
        default=True,
        description="When False, every lookup hits the DB. Useful in tests.",
    )
    wildcard_enabled: bool = Field(
        default=True,
        description="When True, permission names containing '*' are matched as glob patterns.",
    )
    events_enabled: bool = Field(
        default=False,
        description="When True, role/permission mutations dispatch typed events.",
    )
    cache_store: str | None = Field(default=None)
    cache_ttl: int = Field(default=86400, ge=1)
    cache_prefix: str = Field(default="arvel.permission", min_length=1)
