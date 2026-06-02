"""Test-only endpoints — disabled in production."""

from __future__ import annotations

import importlib
from typing import Any

from app.support.products_catalog import refresh_products_catalog
from arvel import Route
from arvel.database.db import DB
from arvel.http.exceptions import NotFoundException
from arvel.support.env import env


async def seed_catalog() -> dict[str, Any]:
    """Test-only seeder trigger. Disabled in production.

    Intentionally has no DB_TX middleware so we can run seeder inserts
    in one transaction and REFRESH MATERIALIZED VIEW in a separate transaction
    after the data is committed (the view query cannot see uncommitted rows).

    """
    if env("APP_ENV", "production").lower() == "production":
        raise NotFoundException("Not found.")
    rbac_mod = importlib.import_module("database.seeders.roles_and_permissions_seeder")
    catalog_mod = importlib.import_module("database.seeders.catalog_seeder")
    users_mod = importlib.import_module("database.seeders.sample_users_seeder")

    async with DB.transaction():
        await rbac_mod.RolesAndPermissionsSeeder().run()
        await catalog_mod.CatalogSeeder().run()
        await users_mod.SampleUsersSeeder().run()

    await refresh_products_catalog()

    return {"status": "seeded"}


async def refresh_catalog() -> dict[str, Any]:
    """Trigger an immediate refresh of the products_catalog materialized view.


    Used by ``make seed`` after ``arvel db:seed`` commits, since the refresh
    must run in a separate transaction to see the newly committed rows.
    Disabled in production.
    """
    if env("APP_ENV", "production").lower() == "production":
        raise NotFoundException("Not found.")
    count = await refresh_products_catalog()
    return {"status": "refreshed", "count": count}


def register_test_routes() -> None:
    """Register test-only routes.


    Called from routes/api.py on every routing reload. Decorators would only
    fire on first import, so a fresh Application would silently lose these routes.
    """
    Route.post("/api/test/seed/catalog", name="api.test.seed.catalog")(seed_catalog)
    Route.post("/api/test/catalog/refresh", name="api.test.catalog.refresh")(refresh_catalog)
