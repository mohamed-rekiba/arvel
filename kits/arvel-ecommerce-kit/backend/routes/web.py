"""Web routes — SPA catch-all; no server-rendered pages in this kit."""

from __future__ import annotations

from pathlib import Path

from arvel import Route
from starlette.responses import FileResponse, HTMLResponse, Response

_FRONTEND_DIR = Path(__file__).resolve().parents[1].parent / "frontend"
_DIST_DIR = _FRONTEND_DIR / "dist"
_INDEX_FILE = _DIST_DIR / "index.html"

_SPA_FALLBACK = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Arvel E-Commerce Kit</title>
  </head>
  <body>
    <div id="app">Build the Vue frontend with <code>npm run build</code>.</div>
  </body>
</html>
"""


def _spa_shell() -> Response:
    if _INDEX_FILE.exists():
        return FileResponse(_INDEX_FILE)
    return HTMLResponse(_SPA_FALLBACK)


@Route.get("/", name="web.storefront.home", include_in_schema=False)
@Route.get("/login", name="web.storefront.login", include_in_schema=False)
@Route.get("/register", name="web.storefront.register", include_in_schema=False)
@Route.get("/products", name="web.storefront.products", include_in_schema=False)
@Route.get("/products/{slug}", name="web.storefront.products.detail", include_in_schema=False)
@Route.get("/categories/{slug}", name="web.storefront.categories.detail", include_in_schema=False)
@Route.get("/search", name="web.storefront.search", include_in_schema=False)
@Route.get("/cart", name="web.storefront.cart", include_in_schema=False)
@Route.get("/checkout", name="web.storefront.checkout", include_in_schema=False)
@Route.get("/account", name="web.storefront.account", include_in_schema=False)
@Route.get("/account/orders", name="web.storefront.account.orders", include_in_schema=False)
@Route.get("/admin", name="web.admin.dashboard", include_in_schema=False)
@Route.get("/admin/{path:path}", name="web.admin.catch_all", include_in_schema=False)
async def spa_shell() -> Response:
    """Serve the Vue storefront/admin shell."""
    return _spa_shell()


@Route.get("/assets/{path:path}", name="web.assets", include_in_schema=False)
async def spa_asset(path: str) -> Response:
    asset_path = (_DIST_DIR / "assets" / path).resolve()
    assets_root = (_DIST_DIR / "assets").resolve()
    if not asset_path.is_file() or assets_root not in asset_path.parents:
        return _spa_shell()
    return FileResponse(asset_path)
