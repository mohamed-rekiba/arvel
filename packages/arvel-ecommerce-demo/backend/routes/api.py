"""API route registration.

All routes declared here; controllers contain only handler logic.

Route hierarchy:
  Health — GET /healthz
  Auth — POST /api/auth/login, POST /api/auth/register, GET /api/auth/me
  Public — GET /api/products, GET /api/products/{slug},
               GET /api/categories/{slug}/products, GET /api/search
  Cart — /api/cart/*
  Checkout — POST /api/checkout
  Account — /api/account/orders/*
  i18n — GET /api/i18n/{locale}
  Admin — /api/admin/* (products, vendors, categories, users, orders, roles, translations)
  Test — /api/test/* (seed endpoints, disabled in production)
"""

from __future__ import annotations

from app.http.controllers import test as _test
from app.http.controllers._deps import DB_TX
from app.http.controllers.account import AccountController
from app.http.controllers.admin.categories import AdminCategoriesController
from app.http.controllers.admin.orders import AdminOrdersController
from app.http.controllers.admin.products import AdminProductsController
from app.http.controllers.admin.roles import AdminRolesController
from app.http.controllers.admin.translations import AdminTranslationsController
from app.http.controllers.admin.users import AdminUsersController
from app.http.controllers.admin.vendors import AdminVendorsController
from app.http.controllers.auth import EcommerceAuthController as AuthController
from app.http.controllers.cart import CartController
from app.http.controllers.checkout import CheckoutController
from app.http.controllers.i18n import I18nController
from app.http.controllers.storefront import StorefrontController
from arvel import Route


@Route.get("/healthz", name="healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


# ─── Auth ─────────────────────────────────────────────────────────────────────

with Route.group(prefix="/api/auth", name_prefix="auth.", middleware=DB_TX, tags=["Auth"]):
    Route.post("/login", controller=AuthController, action="login", name="login")
    Route.post("/register", controller=AuthController, action="register", name="register")
    Route.get("/me", controller=AuthController, action="me", name="me")


# ─── Public storefront ────────────────────────────────────────────────────────

with Route.group(prefix="/api", name_prefix="storefront.", middleware=DB_TX, tags=["Storefront"]):
    Route.get("/products", controller=StorefrontController, action="index", name="index")
    Route.get("/products/{slug}", controller=StorefrontController, action="show", name="show")
    # /categories must be registered before /{slug} variants to avoid shadowing
    Route.get(
        "/categories",
        controller=StorefrontController,
        action="categories_index",
        name="categories.index",
    )
    Route.get(
        "/categories/{slug}",
        controller=StorefrontController,
        action="products_catalog",
        name="products_catalog",
    )
    Route.get(
        "/categories/{slug}/products",
        controller=StorefrontController,
        action="products_catalog",
        name="products_catalog_alt",
    )
    Route.get("/search", controller=StorefrontController, action="search", name="search")


# ─── Cart ─────────────────────────────────────────────────────────────────────

with Route.group(prefix="/api/cart", name_prefix="cart.", middleware=DB_TX, tags=["Cart"]):
    Route.get("", controller=CartController, action="show", name="show")
    Route.post("/items", controller=CartController, action="add_item", name="items.store")
    Route.patch(
        "/items/{item_id}",
        controller=CartController,
        action="update_item",
        name="items.update",
    )
    Route.delete(
        "/items/{item_id}",
        controller=CartController,
        action="remove_item",
        name="items.destroy",
    )


# ─── Checkout ─────────────────────────────────────────────────────────────────

with Route.group(prefix="/api", middleware=DB_TX, tags=["Checkout"]):
    Route.post(
        "/checkout",
        controller=CheckoutController,
        action="checkout",
        name="checkout",
        status_code=201,
    )


# ─── Account ──────────────────────────────────────────────────────────────────

with Route.group(prefix="/api/account", name_prefix="account.", middleware=DB_TX, tags=["Account"]):
    Route.get("/orders", controller=AccountController, action="list_orders", name="orders.index")
    Route.get(
        "/orders/{order_id}",
        controller=AccountController,
        action="show_order",
        name="orders.show",
    )


# ─── i18n ─────────────────────────────────────────────────────────────────────

with Route.group(prefix="/api/i18n", name_prefix="i18n.", tags=["I18n"]):
    Route.get("/{locale}", controller=I18nController, action="catalogue", name="catalogue")


# ─── Admin ────────────────────────────────────────────────────────────────────

with Route.group(prefix="/api/admin", name_prefix="admin.", middleware=DB_TX):
    # Products
    with Route.group(prefix="/products", name_prefix="products.", tags=["Admin Products"]):
        Route.get("", controller=AdminProductsController, action="index", name="index")
        Route.post(
            "", controller=AdminProductsController, action="store", name="store", status_code=201
        )
        # catalog/refresh must come before /{product_id} to avoid shadowing
        Route.post(
            "/catalog/refresh",
            controller=AdminProductsController,
            action="catalog_refresh",
            name="catalog.refresh",
        )
        Route.get(
            "/{product_id}",
            controller=AdminProductsController,
            action="show",
            name="show",
        )
        Route.patch(
            "/{product_id}",
            controller=AdminProductsController,
            action="update",
            name="update",
        )
        Route.delete(
            "/{product_id}",
            controller=AdminProductsController,
            action="destroy",
            name="destroy",
        )
        Route.delete(
            "/{product_id}/force",
            controller=AdminProductsController,
            action="force_destroy",
            name="force_destroy",
        )
        Route.post(
            "/{product_id}/restore",
            controller=AdminProductsController,
            action="restore",
            name="restore",
        )
        Route.patch(
            "/{product_id}/publish",
            controller=AdminProductsController,
            action="publish",
            name="publish",
        )
        Route.patch(
            "/{product_id}/unpublish",
            controller=AdminProductsController,
            action="unpublish",
            name="unpublish",
        )
        Route.get(
            "/{product_id}/media",
            controller=AdminProductsController,
            action="media_index",
            name="media.index",
        )
        Route.post(
            "/{product_id}/media",
            controller=AdminProductsController,
            action="media_store",
            name="media.store",
            status_code=201,
        )
        Route.delete(
            "/{product_id}/media/{media_id}",
            controller=AdminProductsController,
            action="media_destroy",
            name="media.destroy",
        )

    # Categories
    with Route.group(prefix="/categories", name_prefix="categories.", tags=["Admin Categories"]):
        Route.get("", controller=AdminCategoriesController, action="index", name="index")
        Route.post(
            "", controller=AdminCategoriesController, action="store", name="store", status_code=201
        )
        Route.get(
            "/{category_id}",
            controller=AdminCategoriesController,
            action="show",
            name="show",
        )
        Route.patch(
            "/{category_id}",
            controller=AdminCategoriesController,
            action="update",
            name="update",
        )
        Route.delete(
            "/{category_id}",
            controller=AdminCategoriesController,
            action="destroy",
            name="destroy",
        )
        Route.delete(
            "/{category_id}/force",
            controller=AdminCategoriesController,
            action="force_destroy",
            name="force_destroy",
        )
        Route.post(
            "/{category_id}/restore",
            controller=AdminCategoriesController,
            action="restore",
            name="restore",
        )
        Route.patch(
            "/{category_id}/publish",
            controller=AdminCategoriesController,
            action="publish",
            name="publish",
        )
        Route.patch(
            "/{category_id}/unpublish",
            controller=AdminCategoriesController,
            action="unpublish",
            name="unpublish",
        )

    # Vendors
    with Route.group(prefix="/vendors", name_prefix="vendors.", tags=["Admin Vendors"]):
        Route.get("", controller=AdminVendorsController, action="index", name="index")
        Route.post(
            "", controller=AdminVendorsController, action="store", name="store", status_code=201
        )
        Route.get(
            "/{vendor_id}",
            controller=AdminVendorsController,
            action="show",
            name="show",
        )
        Route.patch(
            "/{vendor_id}",
            controller=AdminVendorsController,
            action="update",
            name="update",
        )
        Route.delete(
            "/{vendor_id}",
            controller=AdminVendorsController,
            action="destroy",
            name="destroy",
        )
        Route.delete(
            "/{vendor_id}/force",
            controller=AdminVendorsController,
            action="force_destroy",
            name="force_destroy",
        )
        Route.post(
            "/{vendor_id}/restore",
            controller=AdminVendorsController,
            action="restore",
            name="restore",
        )
        Route.patch(
            "/{vendor_id}/publish",
            controller=AdminVendorsController,
            action="publish",
            name="publish",
        )
        Route.patch(
            "/{vendor_id}/unpublish",
            controller=AdminVendorsController,
            action="unpublish",
            name="unpublish",
        )

    # Orders
    with Route.group(prefix="/orders", name_prefix="orders.", tags=["Admin Orders"]):
        Route.get("", controller=AdminOrdersController, action="index", name="index")
        # Static segments must come before /{order_id} to avoid route conflicts.
        Route.get(
            "/best-sellers",
            controller=AdminOrdersController,
            action="best_sellers",
            name="best_sellers",
        )
        Route.get(
            "/{order_id}",
            controller=AdminOrdersController,
            action="show",
            name="show",
        )
        Route.patch(
            "/{order_id}/status",
            controller=AdminOrdersController,
            action="update_status",
            name="update_status",
        )

    # Users
    with Route.group(prefix="/users", name_prefix="users.", tags=["Admin Users"]):
        Route.get("", controller=AdminUsersController, action="index", name="index")
        Route.get("/{user_id}", controller=AdminUsersController, action="show", name="show")
        Route.delete(
            "/{user_id}", controller=AdminUsersController, action="destroy", name="destroy"
        )
        Route.delete(
            "/{user_id}/force",
            controller=AdminUsersController,
            action="force_destroy",
            name="force_destroy",
        )
        Route.post(
            "/{user_id}/restore",
            controller=AdminUsersController,
            action="restore",
            name="restore",
        )
        Route.patch(
            "/{user_id}/suspend",
            controller=AdminUsersController,
            action="suspend",
            name="suspend",
        )
        Route.patch(
            "/{user_id}/unsuspend",
            controller=AdminUsersController,
            action="unsuspend",
            name="unsuspend",
        )
        Route.post(
            "/{user_id}/roles",
            controller=AdminUsersController,
            action="assign_role",
            name="roles.assign",
        )
        Route.delete(
            "/{user_id}/roles",
            controller=AdminUsersController,
            action="revoke_role",
            name="roles.revoke",
        )
        Route.post(
            "/{user_id}/permissions",
            controller=AdminUsersController,
            action="grant_permission",
            name="permissions.grant",
        )
        Route.delete(
            "/{user_id}/permissions",
            controller=AdminUsersController,
            action="revoke_permission",
            name="permissions.revoke",
        )

    # Roles
    with Route.group(prefix="/roles", name_prefix="roles.", tags=["Admin Roles Permissions"]):
        Route.get("", controller=AdminRolesController, action="index", name="index")
        Route.get(
            "/permissions",
            controller=AdminRolesController,
            action="permissions_index",
            name="permissions.index",
        )

    # Translations
    with Route.group(
        prefix="/translations", name_prefix="translations.", tags=["Admin Translations"]
    ):
        Route.get("", controller=AdminTranslationsController, action="index", name="index")


# ─── Test-only ──────────────────────────────────────────────────────────────
# Registered via a call (not import side-effect) so they survive routing reloads
# when a fresh Application is built per integration test.
_test.register_test_routes()
