"""Async application factory for the e-commerce kit integration tests.

Production runs via ``public/asgi.py``. Integration tests import this
module and call ``await create_app()`` which boots the framework in-process
and returns an :class:`EcommerceApp` that is:

- ASGI-callable (delegates to FastAPI via ``__call__``)
- Seedable via ``.seed(name)``
- Cleanly teardown-able via ``.shutdown()``
"""

from __future__ import annotations

import importlib
from typing import Any

from arvel.application._loader import clear_module_cache
from arvel.database.db import DB
from bootstrap.app import create_application, create_asgi

from app.support.products_catalog import refresh_products_catalog_now


class EcommerceApp:
    """ASGI-callable wrapper over the booted Arvel Application."""

    def __init__(self, arvel_app: Any, asgi_app: Any) -> None:
        self._arvel_app = arvel_app
        self._asgi_app = asgi_app

    @property
    def asgi(self) -> Any:
        return self._asgi_app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        await self._asgi_app(scope, receive, send)

    async def seed(self, name: str) -> None:
        """Run the named seeder group in-process.


        Wrapped in DB.transaction() so every upsert shares one committed
        session — without this, each DB.select() would create its own
        session that auto-rolls-back, leaving FK references dangling.
        """
        rbac_mod = importlib.import_module("database.seeders.roles_and_permissions_seeder")
        catalog_mod = importlib.import_module("database.seeders.catalog_seeder")
        users_mod = importlib.import_module("database.seeders.sample_users_seeder")

        if name == "catalog":
            async with DB.transaction():
                await rbac_mod.RolesAndPermissionsSeeder().run()
                await catalog_mod.CatalogSeeder().run()
                await users_mod.SampleUsersSeeder().run()
            # Separate session: REFRESH sees committed rows.
            await refresh_products_catalog_now()

    async def shutdown(self) -> None:
        await self._arvel_app.shutdown()


async def create_app() -> EcommerceApp:
    """Build, boot, and return the kit application as an ASGI-callable wrapper."""
    # Env vars like DB_URL change between test fixtures; force fresh config reads.
    clear_module_cache()
    arvel_app = create_application()
    await arvel_app.boot()
    asgi_app = create_asgi(arvel_app)
    return EcommerceApp(arvel_app, asgi_app)
