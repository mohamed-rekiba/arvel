"""Seed roles, permissions, and the Super Admin user.

Role name == slug (snake_case) for direct `has_role()` compatibility.

Roles:
- super_admin  — full access, including force-delete and user management
- admin        — everything except force-delete
- catalog_manager — products, categories, vendors, media
- order_manager — order operations
- support_agent — read-only admin + order status updates
- customer     — storefront only; no admin access

Permissions follow the format ``<resource>.<action>``.
"""

from __future__ import annotations

import os

from app.support.seeder import EcommerceSeeder


class RolesAndPermissionsSeeder(EcommerceSeeder):
    async def run(self) -> None:
        roles_data: list[dict[str, object]] = [
            {"name": "super_admin", "guard_name": "api", "level": 100},
            {"name": "admin", "guard_name": "api", "level": 80},
            {"name": "catalog_manager", "guard_name": "api", "level": 60},
            {"name": "order_manager", "guard_name": "api", "level": 60},
            {"name": "support_agent", "guard_name": "api", "level": 40},
            {"name": "customer", "guard_name": "api", "level": 0},
        ]

        permissions_data: list[str] = [
            "products.view",
            "products.create",
            "products.update",
            "products.delete",
            "products.publish",
            "products.restore",
            "categories.*",
            "orders.*",
            "categories.view",
            "categories.create",
            "categories.update",
            "categories.delete",
            "vendors.view",
            "vendors.create",
            "vendors.update",
            "vendors.delete",
            "orders.view",
            "orders.update",
            # users.view is used by the admin sidebar nav (read-only user list)
            # users.manage covers write operations (suspend, delete, role assign)
            "users.view",
            "users.manage",
            "roles.manage",
            "analytics.view",
            "settings.view",
            "media.upload",
            "media.delete",
        ]

        role_permissions: dict[str, list[str]] = {
            "catalog_manager": [
                "products.view",
                "products.create",
                "products.update",
                "products.delete",
                "products.publish",
                "products.restore",
                "categories.*",
                "categories.view",
                "categories.create",
                "categories.update",
                "categories.delete",
                "vendors.view",
                "vendors.create",
                "vendors.update",
                "vendors.delete",
                "media.upload",
                "media.delete",
            ],
            "order_manager": [
                "orders.*",
                "orders.view",
                "orders.update",
            ],
            "support_agent": [
                "products.view",
                "categories.view",
                "vendors.view",
                "orders.*",
                "orders.view",
                "orders.update",
                "users.view",
            ],
            "admin": [
                "products.view",
                "products.create",
                "products.update",
                "products.delete",
                "products.publish",
                "products.restore",
                "categories.*",
                "categories.view",
                "categories.create",
                "categories.update",
                "categories.delete",
                "vendors.view",
                "vendors.create",
                "vendors.update",
                "vendors.delete",
                "orders.*",
                "orders.view",
                "orders.update",
                "users.view",
                "users.manage",
                "analytics.view",
                "settings.view",
                "media.upload",
                "media.delete",
            ],
            "super_admin": list(permissions_data),
        }

        for perm_slug in permissions_data:
            await self.db.upsert(
                "permissions",
                match_on=["name", "guard_name"],
                data={"name": perm_slug, "guard_name": "api"},
            )

        for role_data in roles_data:
            await self.db.upsert(
                "roles",
                match_on=["name", "guard_name"],
                data=role_data,
            )

        for role_name, perms in role_permissions.items():
            role_row = await self.db.table("roles").where("name", role_name).first()
            if not role_row:
                continue
            for perm_slug in perms:
                perm = await self.db.table("permissions").where("name", perm_slug).first()
                if not perm:
                    continue
                await self.db.upsert(
                    "role_has_permissions",
                    match_on=["role_id", "permission_id"],
                    data={"role_id": role_row["id"], "permission_id": perm["id"]},
                )

        admin_email = os.environ.get("ADMIN_SEED_EMAIL", "admin@example.com")
        admin_password = os.environ.get("ADMIN_SEED_PASSWORD", "AdminPwd!1")

        admin_user = await self.db.upsert(
            "users",
            match_on=["email"],
            data={
                "name": "Super Admin",
                "email": admin_email,
                "password": self.hash_password(admin_password),
                "email_verified_at": self.now(),
                "locale": "en",
                "theme": "system",
            },
            cast_map={"theme": "users_theme"},
        )

        sa_role = await self.db.table("roles").where("name", "super_admin").first()
        if sa_role and admin_user:
            await self.db.upsert(
                "model_has_roles",
                match_on=["role_id", "model_id", "model_type"],
                data={
                    "role_id": sa_role["id"],
                    "model_id": str(admin_user["id"]),
                    "model_type": "User",
                    "guard_name": "api",
                },
            )
