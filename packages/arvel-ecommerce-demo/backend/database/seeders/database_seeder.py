"""DatabaseSeeder — orchestrator for ``arvel db:seed``.

Runs the demo's seeders in dependency order:

1. :class:`RolesAndPermissionsSeeder` — RBAC skeleton + super-admin account.
2. :class:`CatalogSeeder` — vendor, categories, products, and media.
3. :class:`DemoUsersSeeder` — role-scoped demo accounts (depends on roles).
"""

from __future__ import annotations

from app.support.products_catalog import refresh_products_catalog
from arvel.database import DatabaseSeeder as _BaseDatabaseSeeder
from database.seeders.catalog_seeder import CatalogSeeder
from database.seeders.demo_users_seeder import DemoUsersSeeder
from database.seeders.roles_and_permissions_seeder import RolesAndPermissionsSeeder


class DatabaseSeeder(_BaseDatabaseSeeder):
    async def run(self) -> None:
        await super().run()  # production guard
        await RolesAndPermissionsSeeder().run()
        await CatalogSeeder().run()
        await DemoUsersSeeder().run()
        await refresh_products_catalog()
