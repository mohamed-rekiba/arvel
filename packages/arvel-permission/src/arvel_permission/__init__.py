"""arvel-permission — Spatie Laravel Permission v7 feature parity for Arvel.

Supplies the ``Role`` and ``Permission`` SQLAlchemy models, the ``HasRoles``
and ``HasPermissions`` mixins, an async ``PermissionRegistrar``, and a
``PermissionServiceProvider`` that registers permission-aware ability checks
with the Arvel ``Gate``.
"""

from __future__ import annotations

from arvel_permission.config import PermissionConfig
from arvel_permission.exceptions import (
    PermissionDoesNotExist,
    RoleDoesNotExist,
    UnauthorizedException,
)
from arvel_permission.gate_integration import register_permissions_with_gate
from arvel_permission.middleware import (
    PermissionMiddleware,
    RoleMiddleware,
    RoleOrPermissionMiddleware,
)
from arvel_permission.models import (
    Permission,
    Role,
    model_has_permissions,
    model_has_roles,
    role_has_permissions,
)
from arvel_permission.provider import PermissionServiceProvider
from arvel_permission.service import GuardMismatchError, PermissionRegistrar
from arvel_permission.traits import HasPermissions, HasRoles

__all__ = [
    "GuardMismatchError",
    "HasPermissions",
    "HasRoles",
    "Permission",
    "PermissionConfig",
    "PermissionDoesNotExist",
    "PermissionMiddleware",
    "PermissionRegistrar",
    "PermissionServiceProvider",
    "Role",
    "RoleDoesNotExist",
    "RoleMiddleware",
    "RoleOrPermissionMiddleware",
    "UnauthorizedException",
    "model_has_permissions",
    "model_has_roles",
    "register_permissions_with_gate",
    "role_has_permissions",
]
