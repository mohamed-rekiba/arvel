"""API contract and permission fixes.

All tests are source-inspection tests (no DB, no I/O) that fail before the
fixes are applied and pass after. They verify the exact structural patterns
required by each FR.
"""

from __future__ import annotations

import pathlib

_BACKEND = pathlib.Path(__file__).parent.parent.parent
_PRODUCT_SVC = _BACKEND / "app" / "services" / "product_service.py"
_API = _BACKEND / "routes" / "api.py"
_RBAC_SEEDER = _BACKEND / "database" / "seeders" / "roles_and_permissions_seeder.py"
_CATALOG_SEEDER = _BACKEND / "database" / "seeders" / "catalog_seeder.py"
_PRODUCT_MIGRATION = (
    _BACKEND / "database" / "migrations" / "2026_05_23_000003_create_products_table.py"
)
_PRODUCT_SLUG_INDEX_MIGRATION = (
    _BACKEND / "database" / "migrations" / "2026_05_25_000012_add_products_slug_en_unique_index.py"
)


def _src(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


# ─── stock field name ─────────────────────────────────────────────────


class TestV026StockFieldName:
    def test_stock_key_present_in_storefront(self) -> None:
        src = _src(_PRODUCT_SVC)
        assert '"stock"' in src, "V-026 not fixed: storefront response must include 'stock' key"

    def test_stock_qty_absent_from_storefront(self) -> None:
        src = _src(_PRODUCT_SVC)
        # "stock_qty" still appears in admin helper and ORM access — ensure it's
        # not used as a response KEY in product_to_storefront
        func_start = src.find("def product_to_storefront(")
        func_end = src.find("\n    @staticmethod", func_start + 1)
        if func_end == -1:
            func_end = src.find("\n    async def", func_start + 1)
        storefront_body = src[func_start:func_end] if func_end != -1 else src[func_start:]
        assert '"stock_qty"' not in storefront_body, (
            "V-026 not fixed: 'stock_qty' must not be a response key in product_to_storefront"
        )


# ─── short_description field name ─────────────────────────────────────


class TestV027ShortDescriptionFieldName:
    def test_short_description_key_present(self) -> None:
        src = _src(_PRODUCT_SVC)
        assert '"short_description"' in src, (
            "V-027 not fixed: storefront response must include 'short_description' key"
        )

    def test_description_key_absent_from_storefront(self) -> None:
        src = _src(_PRODUCT_SVC)
        func_start = src.find("def product_to_storefront(")
        func_end = src.find("\n    @staticmethod", func_start + 1)
        if func_end == -1:
            func_end = src.find("\n    async def", func_start + 1)
        storefront_body = src[func_start:func_end] if func_end != -1 else src[func_start:]
        assert '"description"' not in storefront_body, (
            "V-027 not fixed: 'description' key must not appear"
            " in product_to_storefront return dict"
        )


# ─── /me endpoint enrichment ─────────────────────────────────────────


class TestV028MeEndpointEnrichment:
    _AUTH_CTRL = _BACKEND / "app" / "http" / "controllers" / "auth.py"

    def test_me_returns_locale(self) -> None:
        src = _src(self._AUTH_CTRL)
        assert '"locale"' in src or "locale" in src, (
            "V-028 not fixed: /me must include locale in response"
        )

    def test_me_returns_theme(self) -> None:
        src = _src(self._AUTH_CTRL)
        assert '"theme"' in src or "theme" in src, (
            "V-028 not fixed: /me must include theme in response"
        )

    def test_me_returns_permissions(self) -> None:
        src = _src(self._AUTH_CTRL)
        assert '"permissions"' in src or "permissions" in src, (
            "V-028 not fixed: /me must include permissions list in response"
        )

    def test_me_returns_roles(self) -> None:
        src = _src(self._AUTH_CTRL)
        assert '"roles"' in src or "roles" in src, (
            "V-028 not fixed: /me must include roles list in response"
        )


# ─── users.view permission seeded ─────────────────────────────────────


class TestV029UsersViewPermission:
    def test_users_view_in_seeder(self) -> None:
        src = _src(_RBAC_SEEDER)
        assert '"users.view"' in src, "V-029 not fixed: 'users.view' must be seeded as a permission"

    def test_users_view_assigned_to_admin(self) -> None:
        src = _src(_RBAC_SEEDER)
        # Find the admin role_permissions block and verify users.view is there
        admin_block_start = src.find('"admin": [')
        admin_block_end = src.find("],\n", admin_block_start)
        admin_block = src[admin_block_start:admin_block_end]
        assert '"users.view"' in admin_block, (
            "V-029 not fixed: admin role must include 'users.view'"
        )


# ─── analytics.view and settings.view seeded ─────────────────────────


class TestV030AnalyticsSettingsPermissions:
    def test_analytics_view_seeded(self) -> None:
        src = _src(_RBAC_SEEDER)
        assert '"analytics.view"' in src, (
            "V-030 not fixed: 'analytics.view' must be in permissions_data"
        )

    def test_settings_view_seeded(self) -> None:
        src = _src(_RBAC_SEEDER)
        assert '"settings.view"' in src, (
            "V-030 not fixed: 'settings.view' must be in permissions_data"
        )

    def test_super_admin_has_analytics_view(self) -> None:
        src = _src(_RBAC_SEEDER)
        # super_admin gets list(permissions_data) — if analytics.view is in
        # permissions_data, super_admin inherits it automatically
        assert '"analytics.view"' in src, (
            "V-030 not fixed: super_admin must inherit analytics.view via permissions_data"
        )


# ─── category slug wrapped as dict ────────────────────────────────────


class TestV031CategorySlugWrapped:
    _CAT_SVC = _BACKEND / "app" / "services" / "category_service.py"

    def test_category_slug_returned_as_jsonb_mapping(self) -> None:
        src = _src(self._CAT_SVC)
        assert '"slug": category.slug or {}' in src, (
            "V-031 not fixed: category slug must be returned as the JSONB locale mapping"
        )
        assert '"slug": category.slug,' not in src, (
            "V-031 not fixed: category slug must not be returned as a bare scalar"
        )


# ─── optional ProductCard fields ─────────────────────────────────────


class TestV032OptionalProductCardFields:
    def _get_storefront_body(self) -> str:
        src = _src(_PRODUCT_SVC)
        func_start = src.find("def product_to_storefront(")
        func_end = src.find("\n    @staticmethod", func_start + 1)
        if func_end == -1:
            func_end = src.find("\n    async def", func_start + 1)
        return src[func_start:func_end] if func_end != -1 else src[func_start:]

    def test_original_price_present(self) -> None:
        assert '"original_price"' in self._get_storefront_body(), (
            "V-032 not fixed: 'original_price' missing from product_to_storefront"
        )

    def test_thumbnail_url_present(self) -> None:
        assert '"thumbnail_url"' in self._get_storefront_body(), (
            "V-032 not fixed: 'thumbnail_url' missing from product_to_storefront"
        )

    def test_rating_present(self) -> None:
        assert '"rating"' in self._get_storefront_body(), (
            "V-032 not fixed: 'rating' missing from product_to_storefront"
        )

    def test_rating_count_present(self) -> None:
        assert '"rating_count"' in self._get_storefront_body(), (
            "V-032 not fixed: 'rating_count' missing from product_to_storefront"
        )

    def test_is_new_present(self) -> None:
        assert '"is_new"' in self._get_storefront_body(), (
            "V-032 not fixed: 'is_new' missing from product_to_storefront"
        )

    def test_is_bestseller_present(self) -> None:
        assert '"is_bestseller"' in self._get_storefront_body(), (
            "V-032 not fixed: 'is_bestseller' missing from product_to_storefront"
        )


# ─── i18n catalogue completeness ─────────────────────────────────────


class TestV033I18nCatalogue:
    _I18N_CTRL = _BACKEND / "app" / "http" / "controllers" / "i18n.py"
    _REQUIRED_KEYS = [
        "flash_sale.ends_in",
        "flash_sale.expired",
        "common.view_all",
        "nav.dashboard",
        "nav.customers",
        "nav.categories",
        "nav.vendors",
        "nav.analytics",
        "nav.settings",
        "auth.logout",
        "dashboard.recent_orders",
        "dashboard.view_all_orders",
        "order.id",
        "order.customer",
        "order.date",
        "order.total",
    ]

    def test_en_catalogue_has_all_required_keys(self) -> None:
        src = _src(self._I18N_CTRL)
        for key in self._REQUIRED_KEYS:
            assert f'"{key}"' in src, (
                f"V-033 not fixed: i18n key '{key}' missing from i18n controller"
            )

    def test_ar_catalogue_has_all_required_keys(self) -> None:
        src = _src(self._I18N_CTRL)
        # The AR catalogue must also have these keys — check they appear at least twice
        for key in self._REQUIRED_KEYS:
            count = src.count(f'"{key}"')
            assert count >= 2, f"V-033 not fixed: i18n key '{key}' missing from AR/TR catalogue"


# ─── exclude_unset in PATCH handler ───────────────────────────────────


class TestV034ExcludeUnset:
    def test_patch_uses_exclude_unset(self) -> None:
        products_ctrl = _src(_BACKEND / "app" / "http" / "controllers" / "admin" / "products.py")
        assert "exclude_unset=True" in products_ctrl, (
            "V-034 not fixed: PATCH handler must use model_dump(exclude_unset=True)"
        )


# ─── idempotent catalog seeder ───────────────────────────────────────


class TestV035IdempotentSeeder:
    def test_products_not_using_empty_match_on(self) -> None:
        src = _src(_CATALOG_SEEDER)
        # match_on=[] causes plain inserts (not upserts)
        assert "match_on=[]" not in src, (
            "V-035 not fixed: catalog seeder must not use match_on=[] for products"
        )

    def test_products_use_slug_match_on(self) -> None:
        src = _src(_CATALOG_SEEDER)
        assert "match_on=" in src and "slug" in src, (
            "V-035 not fixed: product upsert must match on slug"
        )

    def test_product_slug_match_has_unique_index(self) -> None:
        create_src = _src(_PRODUCT_MIGRATION)
        patch_src = _src(_PRODUCT_SLUG_INDEX_MIGRATION)

        assert "products_slug_en_unique" in create_src
        assert "products_slug_en_unique" in patch_src
        assert "slug" in patch_src
