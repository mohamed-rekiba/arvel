"""Prompt surface contract tests for the Vue storefront/admin shell."""

from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).parents[2]
COMPOSE_FILE = BASE_DIR.parent / "docker-compose.yml"
FRONTEND_DIR = BASE_DIR.parent / "frontend"
WEB_ROUTES = BASE_DIR / "routes" / "web.py"


def _src(path: Path) -> str:
    return path.read_text()


def test_frontend_has_runnable_vite_entrypoint() -> None:
    package_json = json.loads((FRONTEND_DIR / "package.json").read_text())

    assert package_json["scripts"]["build"] == "vue-tsc --noEmit && vite build"
    assert (FRONTEND_DIR / "index.html").exists()
    assert (FRONTEND_DIR / "src" / "main.ts").exists()
    assert (FRONTEND_DIR / "src" / "App.vue").exists()


def test_compose_starts_frontend_after_backend_health() -> None:
    compose = _src(COMPOSE_FILE)

    assert "NPM_CONFIG_UPDATE_NOTIFIER" in compose
    assert "pip install --no-cache-dir --root-user-action=ignore uv==0.11.16" in compose
    assert (
        "CACHE_URL: redis://:${REDIS_PASSWORD:-arvel_local_redis_password}@redis:6379/0" in compose
    )
    assert "image: postgres:18.4-bookworm" in compose
    assert "--auth-local=scram-sha-256 --auth-host=scram-sha-256" in compose
    assert "--requirepass" in compose
    backend_block = compose[compose.index("  backend:") : compose.index("  frontend:")]
    assert "start_period: 240s" in backend_block
    frontend_block = compose[compose.index("  frontend:") : compose.index("  scheduler:")]
    assert "VITE_DEV_PROXY_TARGET: http://backend:8001" in frontend_block
    assert "condition: service_healthy" in frontend_block
    assert (FRONTEND_DIR / "src" / "lib" / "api.ts").exists()


def test_frontend_router_declares_prompt_surfaces() -> None:
    src = _src(FRONTEND_DIR / "src" / "router.ts")

    for route in (
        "path: '/'",
        "path: '/login'",
        "path: '/register'",
        "path: '/products'",
        "path: '/search'",
        "path: '/products/:slug'",
        "path: '/categories/:slug'",
        "path: '/cart'",
        "path: '/checkout'",
        "path: '/account'",
        "path: '/account/orders'",
        "path: '/admin/login'",
        "path: '/admin'",
        "path: '/admin/orders'",
        "path: '/admin/users'",
        "path: '/admin/:pathMatch(.*)*'",
    ):
        assert route in src
    # The /admin catch-all must sit inside the requiresAdmin group's children so an
    # unknown /admin/* path is guarded, not rendered unauthenticated at top level.
    children_start = src.index("children: [", src.index("requiresAdmin: true"))
    assert children_start < src.index("admin-catch-all")
    for page in (
        "StorefrontCart",
        "StorefrontCheckout",
        "StorefrontAccount",
        "StorefrontAuth",
        "StorefrontSearch",
        "AdminCatalogPage",
        "AdminListPage",
        "AdminPlaceholderPage",
    ):
        assert page in src


def test_web_routes_serve_spa_shell_for_storefront_and_admin() -> None:
    src = _src(WEB_ROUTES)

    for route in (
        '@Route.get("/", name="web.storefront.home"',
        '@Route.get("/login", name="web.storefront.login"',
        '@Route.get("/register", name="web.storefront.register"',
        '@Route.get("/products", name="web.storefront.products"',
        '@Route.get("/products/{slug}", name="web.storefront.products.detail"',
        '@Route.get("/categories/{slug}", name="web.storefront.categories.detail"',
        '@Route.get("/search", name="web.storefront.search"',
        '@Route.get("/account", name="web.storefront.account"',
        '@Route.get("/account/orders", name="web.storefront.account.orders"',
        '@Route.get("/admin", name="web.admin.dashboard"',
        '@Route.get("/admin/{path:path}", name="web.admin.catch_all"',
        '@Route.get("/assets/{path:path}", name="web.assets"',
    ):
        assert route in src
    assert "FileResponse(_INDEX_FILE)" in src


def test_storefront_pages_use_backend_api_client() -> None:
    # Storefront pages fetch through the generated orval storefront hooks; no
    # hand-rolled lib/api product fetchers and no in-component demo fixtures.
    hooks = {
        "StorefrontHome.vue": "useStorefrontIndexApiProductsGet",
        "StorefrontProducts.vue": "storefrontIndexApiProductsGet",
        "StorefrontProductDetail.vue": "useStorefrontShowApiProductsSlugGet",
    }
    for page, hook in hooks.items():
        src = _src(FRONTEND_DIR / "src" / "pages" / page)
        assert hook in src
        assert "demoProducts" not in src
        assert "fetchProductList" not in src
        assert "fetchProductBySlug" not in src

    assert ':srcset="product.image_srcset || undefined"' in _src(
        FRONTEND_DIR / "src" / "components" / "storefront" / "ProductCard.vue"
    )
    assert ':srcset="product.image_srcset || undefined"' in _src(
        FRONTEND_DIR / "src" / "pages" / "StorefrontProductDetail.vue"
    )


def test_customer_pages_call_cart_checkout_and_account_apis() -> None:
    # Cart mutations go through the generated orval cart hooks in the store;
    # checkout and account orders go through their own generated hooks.
    store = _src(FRONTEND_DIR / "src" / "stores" / "cart.ts")
    for hook in (
        "cartShowApiCartGet",
        "cartItemsStoreApiCartItemsPost",
        "cartItemsUpdateApiCartItemsItemIdPatch",
        "cartItemsDestroyApiCartItemsItemIdDelete",
    ):
        assert hook in store

    checkout = _src(FRONTEND_DIR / "src" / "pages" / "StorefrontCheckout.vue")
    assert "checkoutApiCheckoutPost" in checkout

    account = _src(FRONTEND_DIR / "src" / "pages" / "StorefrontAccount.vue")
    assert "useAccountOrdersIndexApiAccountOrdersGet" in account

    for page in (
        "StorefrontCart.vue",
        "StorefrontCheckout.vue",
        "StorefrontAccount.vue",
        "StorefrontAuth.vue",
        "StorefrontSearch.vue",
    ):
        assert (FRONTEND_DIR / "src" / "pages" / page).exists()

    for page in ("StorefrontCart.vue", "StorefrontCheckout.vue", "StorefrontAccount.vue"):
        src = _src(FRONTEND_DIR / "src" / "pages" / page)
        assert "Paste a bearer token" not in src
        # These pages still gate on a stored session before issuing requests.
        assert "requireStoredAccessToken(" in src


def test_admin_routes_enforce_per_route_permissions() -> None:
    """The router gates each admin route by the backend permission, not just admin access.

    Without this, a deep link to /admin/users (or /admin/roles, etc.) would render
    the shell for any admin and then eat 403s from the API.
    """
    src = _src(FRONTEND_DIR / "src" / "router.ts")

    # Per-route permission metadata mirrors the controllers' require_permission.
    for meta in (
        "permission: 'products.view'",
        "permission: 'products.create'",
        "permission: 'categories.view'",
        "permission: 'vendors.view'",
        "permission: 'orders.view'",
        "permission: 'users.manage'",
        "permission: 'roles.manage'",
        "permission: ['products.view', 'categories.view'], permissionMatch: 'all'",
    ):
        assert meta in src
    # The guard enforces it and falls back to the always-reachable dashboard.
    assert "satisfiesPermission(auth, to.meta.permission, to.meta.permissionMatch)" in src
    assert "return { name: 'admin-dashboard' }" in src


def test_protected_frontend_routes_use_stored_session_guard() -> None:
    router = _src(FRONTEND_DIR / "src" / "router.ts")
    auth_page = _src(FRONTEND_DIR / "src" / "pages" / "StorefrontAuth.vue")

    assert "router.beforeEach(" in router
    assert "hasStoredSession()" in router
    # Guard refreshes the store via the auth store (which hits /api/auth/me),
    # and reuses the store's admin-access check so it can't drift from the nav.
    assert "auth.hydrate()" in router
    assert "auth.hasAdminAccess" in router
    assert "meta: { requiresAuth: true" in router
    assert "meta: { requiresAuth: true, requiresAdmin: true }" in router
    assert "path: '/admin/login'" in router
    # adminRedirect is the declared prop that sends admins to the dashboard;
    # the old undeclared redirectTo prop was dead and fell through to the DOM.
    assert "adminRedirect: true" in router
    assert "route.query.redirect" in auth_page


def test_admin_shell_uses_me_endpoint_for_sidebar_user() -> None:
    store = _src(FRONTEND_DIR / "src" / "stores" / "auth.ts")
    layout = _src(FRONTEND_DIR / "src" / "layouts" / "AdminLayout.vue")

    # The auth store hydrates from the generated /api/auth/me hook.
    assert "authMeApiAuthMeGet(" in store
    assert "async function hydrate(" in store
    assert "auth.hydrate()" in layout
    assert "clearSession()" in layout

    for page in (
        "AdminDashboard.vue",
        "AdminCatalogPage.vue",
        "AdminListPage.vue",
        "AdminPlaceholderPage.vue",
    ):
        src = _src(FRONTEND_DIR / "src" / "pages" / page)
        assert "admin-demo" not in src
        assert "Demo Admin" not in src
        assert '<AdminLayout :user="user">' not in src


def test_admin_dashboard_uses_backend_rows() -> None:
    dashboard = _src(FRONTEND_DIR / "src" / "pages" / "AdminDashboard.vue")

    # KPIs/status come from the DB-aggregated stats hook; the recent-orders card
    # pulls a small page from the orders index hook. No client-side roll-ups.
    assert "useAdminOrdersStatsApiAdminOrdersStatsGet" in dashboard
    assert "useAdminOrdersIndexApiAdminOrdersGet" in dashboard
    assert '@view-order="openOrder"' in dashboard
    assert "prod-linen-shirt" not in dashboard
    assert "ord-1001" not in dashboard


def test_admin_catalog_pages_use_backend_crud_apis() -> None:
    router = _src(FRONTEND_DIR / "src" / "router.ts")
    page = _src(FRONTEND_DIR / "src" / "pages" / "AdminCatalogPage.vue")

    for route in (
        "path: '/admin/products'",
        "path: '/admin/categories'",
        "path: '/admin/vendors'",
    ):
        assert route in router
    # List page reads via the generated orval index hooks (one per resource).
    for snippet in (
        "useAdminProductsIndexApiAdminProductsGet",
        "useAdminCategoriesIndexApiAdminCategoriesGet",
        "useAdminVendorsIndexApiAdminVendorsGet",
    ):
        assert snippet in page
    # Add/Edit navigate to the dedicated create/edit pages instead of an inline modal.
    assert "/admin/${props.catalog}/new" in page
    assert "/admin/${props.catalog}/${id}/edit" in page
    assert "AdminLayout" in page
    assert "Bearer token" not in page


def test_admin_catalog_uses_translatable_inputs() -> None:
    page = _src(FRONTEND_DIR / "src" / "pages" / "AdminCatalogEditPage.vue")
    translatable = _src(FRONTEND_DIR / "src" / "components" / "admin" / "TranslatableInput.vue")

    assert "TranslatableInput" in page
    assert 'v-model="productForm.name"' in page
    assert 'v-model="productForm.description"' in page
    assert "'ar', label: 'Arabic', dir: 'rtl'" in translatable
    assert "'update:modelValue'" in translatable


def test_admin_list_pages_use_backend_read_apis() -> None:
    router = _src(FRONTEND_DIR / "src" / "router.ts")
    page = _src(FRONTEND_DIR / "src" / "pages" / "AdminListPage.vue")

    for route in (
        "path: '/admin/orders'",
        "path: '/admin/users'",
        "path: '/admin/roles'",
        "path: '/admin/permissions'",
        "path: '/admin/translations'",
        "path: '/admin/analytics'",
        "path: '/admin/settings'",
    ):
        assert route in router
    # Orders/users lists read straight from the generated orval index hooks —
    # no hand-rolled lib/api fetch wrapper in between.
    assert "useAdminOrdersIndexApiAdminOrdersGet" in page
    assert "useAdminUsersIndexApiAdminUsersGet" in page
    assert "listAdminRows" not in page
    assert "Bearer token" not in page
    assert (FRONTEND_DIR / "src" / "pages" / "AdminPlaceholderPage.vue").exists()


def test_admin_edit_and_order_detail_routes_use_show_apis() -> None:
    router = _src(FRONTEND_DIR / "src" / "router.ts")
    edit_page = _src(FRONTEND_DIR / "src" / "pages" / "AdminCatalogEditPage.vue")
    order_page = _src(FRONTEND_DIR / "src" / "pages" / "AdminOrderDetailPage.vue")

    for route in (
        "path: '/admin/products/new'",
        "path: '/admin/categories/new'",
        "path: '/admin/vendors/new'",
        "path: '/admin/products/:editId/edit'",
        "path: '/admin/categories/:editId/edit'",
        "path: '/admin/vendors/:editId/edit'",
        "path: '/admin/orders/:orderId'",
    ):
        assert route in router
    # Edit page hydrates from the generated show hooks; create mode skips them.
    assert "useAdminProductsShowApiAdminProductsProductIdGet" in edit_page
    assert "useAdminCategoriesShowApiAdminCategoriesCategoryIdGet" in edit_page
    assert "useAdminVendorsShowApiAdminVendorsVendorIdGet" in edit_page
    assert "useAdminOrdersUpdateStatusApiAdminOrdersOrderIdStatusPatch" in order_page
    assert 'PermissionGate permission="orders.update"' in order_page


def test_admin_user_detail_manages_roles_and_permissions() -> None:
    router = _src(FRONTEND_DIR / "src" / "router.ts")
    api = _src(FRONTEND_DIR / "src" / "lib" / "api.ts")
    list_page = _src(FRONTEND_DIR / "src" / "pages" / "AdminListPage.vue")
    user_page = _src(FRONTEND_DIR / "src" / "pages" / "AdminUserDetailPage.vue")
    routes = _src(BASE_DIR / "routes" / "api.py")
    users = _src(BASE_DIR / "app" / "services" / "user_service.py")

    assert "AdminUserDetailPage" in router
    assert "path: '/admin/users/:userId'" in router
    # The user-detail page is fully Orval-driven — no hand-written lib/api
    # admin-user helpers. The generated mutator still backs every call.
    for hook in (
        "useAdminUsersShowApiAdminUsersUserIdGet",
        "useAdminUsersRolesAssignApiAdminUsersUserIdRolesPost",
        "useAdminUsersRolesRevokeApiAdminUsersUserIdRolesDelete",
        "useAdminUsersForceDestroyApiAdminUsersUserIdForceDelete",
    ):
        assert hook in user_page
    for removed in ("getAdminUser", "assignAdminUserRole", "forceDeleteAdminUser"):
        assert removed not in api, f"{removed} should be replaced by its Orval hook"
    assert "props.resource === 'users'" in list_page
    assert 'id="admin-list-trashed-mode"' in list_page
    assert 'PermissionGate permission="roles.manage"' in user_page
    assert 'PermissionGate permission="users.manage"' in user_page
    assert "forceDelete({ userId: user.id })" in user_page
    assert 'Route.get("/{user_id}"' in routes
    assert '"/{user_id}/force"' in routes
    assert '"roles": roles' in users
    assert '"direct_permissions": direct_permissions' in users
    assert "async def force_delete(self, user_id: int)" in users


def test_admin_product_edit_page_manages_media() -> None:
    api = _src(FRONTEND_DIR / "src" / "lib" / "api.ts")
    page = _src(FRONTEND_DIR / "src" / "pages" / "AdminCatalogEditPage.vue")

    for snippet in (
        "listProductMedia(",
        "uploadProductMedia(",
        "deleteProductMedia(",
        "`/api/admin/products/${encodeURIComponent(productId)}/media`",
    ):
        assert snippet in api
    for snippet in (
        "product_media",
        'type="file"',
        '@change="uploadMedia"',
        "removeMedia(item.id)",
    ):
        assert snippet in page


def test_admin_catalog_actions_use_permission_gate() -> None:
    page = _src(FRONTEND_DIR / "src" / "pages" / "AdminCatalogPage.vue")
    gate = _src(FRONTEND_DIR / "src" / "components" / "admin" / "PermissionGate.vue")
    auth = _src(FRONTEND_DIR / "src" / "composables" / "useAuth.ts")

    assert "PermissionGate" in page
    assert ':permission="publishPermission"' in page
    assert ':permission="deletePermission"' in page
    assert ':permission="createPermission"' in page
    assert 'id="trashed-mode"' in page
    assert "handleForceDelete(record.id)" in page
    assert "hasPermission(props.permission)" in gate
    assert "hasAdminAccess(" in auth
