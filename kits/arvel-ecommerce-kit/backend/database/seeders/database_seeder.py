"""DatabaseSeeder — orchestrator for ``arvel db:seed``.

Runs the kit's seeders in dependency order:

1. :class:`RolesAndPermissionsSeeder` — RBAC skeleton + super-admin account.
2. :class:`CatalogSeeder` — vendor, categories, products, and media.
3. :class:`SampleUsersSeeder` — role-scoped sample accounts (depends on roles).
4. :class:`OrdersSeeder` — sample orders (depends on users + products).
"""

from __future__ import annotations

from app.support.products_catalog import refresh_products_catalog_now
from arvel.database import DatabaseSeeder as _BaseDatabaseSeeder
from arvel.database.db import DB
from database.seeders.catalog_seeder import CatalogSeeder
from database.seeders.orders_seeder import OrdersSeeder
from database.seeders.roles_and_permissions_seeder import RolesAndPermissionsSeeder
from database.seeders.sample_users_seeder import SampleUsersSeeder


class DatabaseSeeder(_BaseDatabaseSeeder):
    async def run(self) -> None:
        await super().run()  # production guard

        await RolesAndPermissionsSeeder().run()
        await CatalogSeeder().run()
        await SampleUsersSeeder().run()
        await OrdersSeeder().run()

        # Refresh after the *outer* transaction commits. Under db:seed the
        # session commits only once run() returns, so an inline refresh on
        # its own autocommit connection would miss the just-seeded rows.
        DB.after_commit(refresh_products_catalog_now)
