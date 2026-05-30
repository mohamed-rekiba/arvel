"""arvel-permission configuration — RBAC pivots and guards."""

from __future__ import annotations

models: dict[str, str] = {
    "permission": "arvel_permission.models.Permission",
    "role": "arvel_permission.models.Role",
}

table_names: dict[str, str] = {
    "roles": "roles",
    "permissions": "permissions",
    "model_has_permissions": "model_has_permissions",
    "model_has_roles": "model_has_roles",
    "role_has_permissions": "role_has_permissions",
}

column_names: dict[str, str] = {
    "role_pivot_key": "role_id",
    "permission_pivot_key": "permission_id",
    "model_morph_key": "model_id",
}

cache: dict[str, object] = {
    "expiration_seconds": 86400,
    "key": "spatie.permission.cache",
    "store": "default",
}
