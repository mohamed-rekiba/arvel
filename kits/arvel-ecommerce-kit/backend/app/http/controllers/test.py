"""Test-only endpoints — enabled only in local/testing environments."""

from __future__ import annotations

import importlib
from typing import Any

from app.support.products_catalog import refresh_products_catalog
from arvel import Route
from arvel.database.db import DB
from arvel.http.exceptions import NotFoundException
from arvel.support.env import env

# Deny-by-default. These reseed/refresh helpers exist for the local dev stack
# and the pytest harness only. Anything else — development, staging, an
# unset APP_ENV, production — gets a 404, so a reachable non-prod deployment
# can't be reseeded by an anonymous caller.
_ALLOWED_ENVS = frozenset({"local", "testing"})


def _guard_test_env() -> None:
    if env("APP_ENV", "production").strip().lower() not in _ALLOWED_ENVS:
        raise NotFoundException("Not found.")


async def seed_catalog() -> dict[str, Any]:
    """Run the catalog seeders. Local/testing only.

    Intentionally has no DB_TX middleware so we can run seeder inserts
    in one transaction and REFRESH MATERIALIZED VIEW in a separate transaction
    after the data is committed (the view query cannot see uncommitted rows).
    """
    _guard_test_env()
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
    """Refresh the products_catalog materialized view. Local/testing only.

    The refresh must run in its own transaction to see newly committed rows.
    """
    _guard_test_env()
    count = await refresh_products_catalog()
    return {"status": "refreshed", "count": count}


def register_test_routes() -> None:
    """Register test-only routes.


    Called from routes/api.py on every routing reload. Decorators would only
    fire on first import, so a fresh Application would silently lose these routes.
    """
    Route.post("/api/test/seed/catalog", name="api.test.seed.catalog")(seed_catalog)
    Route.post("/api/test/catalog/refresh", name="api.test.catalog.refresh")(refresh_catalog)
