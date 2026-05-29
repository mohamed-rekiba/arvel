"""arvel-permission — Spatie Laravel Permission v7 parity for Arvel.

Provides ``Role``, ``Permission`` SQLAlchemy models, ``HasRoles`` and
``HasPermissions`` mixins, an async ``PermissionRegistrar``, and a
``PermissionServiceProvider`` that wires permission-aware ability checks into
the Arvel ``Gate``.

See ``docs/architecture/SAD-025-auth-refresh-spatie-packages.md`` and
``docs/adr/ADR-079-arvel-permission-spatie-parity.md``.
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
    ModelHasPermission,
    ModelHasRole,
    Permission,
    Role,
    RoleHasPermission,
)
from arvel_permission.provider import PermissionServiceProvider
from arvel_permission.service import GuardMismatchError, PermissionRegistrar
from arvel_permission.traits import (
    HasPermissions,
    HasRoles,
    make_permissions_relationship,
    make_roles_relationship,
)

__all__ = [
    "GuardMismatchError",
    "HasPermissions",
    "HasRoles",
    "ModelHasPermission",
    "ModelHasRole",
    "Permission",
    "PermissionConfig",
    "PermissionDoesNotExist",
    "PermissionMiddleware",
    "PermissionRegistrar",
    "PermissionServiceProvider",
    "Role",
    "RoleDoesNotExist",
    "RoleHasPermission",
    "RoleMiddleware",
    "RoleOrPermissionMiddleware",
    "UnauthorizedException",
    "make_permissions_relationship",
    "make_roles_relationship",
    "register_permissions_with_gate",
]
