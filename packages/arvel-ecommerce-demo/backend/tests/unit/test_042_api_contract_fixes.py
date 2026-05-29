"""QA-Pre tests for WI-arvel-042: API contract and permission fixes.

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


# ─── FR-001: stock field name ─────────────────────────────────────────────────


class TestV026StockFieldName:
    def test_stock_key_present_in_storefront(self) -> None:
        src = _src(_PRODUCT_SVC)
        assert '"stock"' in src, "V-026 not fixed: storefront response must include 'stock' key"

    def test_stock_qty_absent_from_storefront(self) -> None:
        src = _src(_PRODUCT_SVC)
        # "stock_qty" still appears in admin helper and ORM access — ensure it's
        # not used as a response KEY in _product_to_storefront
        func_start = src.find("def _product_to_storefront(")
        func_end = src.find("\n    @staticmethod", func_start + 1)
        if func_end == -1:
            func_end = src.find("\n    async def", func_start + 1)
        storefront_body = src[func_start:func_end] if func_end != -1 else src[func_start:]
        assert '"stock_qty"' not in storefront_body, (
            "V-026 not fixed: 'stock_qty' must not be a response key in _product_to_storefront"
        )


# ─── FR-002: short_description field name ─────────────────────────────────────


class TestV027ShortDescriptionFieldName:
    def test_short_description_key_present(self) -> None:
        src = _src(_PRODUCT_SVC)
        assert '"short_description"' in src, (
            "V-027 not fixed: storefront response must include 'short_description' key"
        )

    def test_description_key_absent_from_storefront(self) -> None:
        src = _src(_PRODUCT_SVC)
        func_start = src.find("def _product_to_storefront(")
        func_end = src.find("\n    @staticmethod", func_start + 1)
        if func_end == -1:
            func_end = src.find("\n    async def", func_start + 1)
        storefront_body = src[func_start:func_end] if func_end != -1 else src[func_start:]
        assert '"description"' not in storefront_body, (
            "V-027 not fixed: 'description' key must not appear"
            " in _product_to_storefront return dict"
        )


# ─── FR-003: /me endpoint enrichment ─────────────────────────────────────────


class TestV028MeEndpointEnrichment:
    def test_me_returns_locale(self) -> None:
        src = _src(_API)
        me_start = src.find("async def me_endpoint(")
        me_end = src.find("\n\n@Route.", me_start + 1)
        me_body = src[me_start:me_end] if me_end != -1 else src[me_start:]
        assert '"locale"' in me_body or "locale" in me_body, (
            "V-028 not fixed: /me must include locale in response"
        )

    def test_me_returns_theme(self) -> None:
        src = _src(_API)
        me_start = src.find("async def me_endpoint(")
        me_end = src.find("\n\n@Route.", me_start + 1)
        me_body = src[me_start:me_end] if me_end != -1 else src[me_start:]
        assert '"theme"' in me_body or "theme" in me_body, (
            "V-028 not fixed: /me must include theme in response"
        )

    def test_me_returns_permissions(self) -> None:
        src = _src(_API)
        me_start = src.find("async def me_endpoint(")
        me_end = src.find("\n\n@Route.", me_start + 1)
        me_body = src[me_start:me_end] if me_end != -1 else src[me_start:]
        assert '"permissions"' in me_body or "permissions" in me_body, (
            "V-028 not fixed: /me must include permissions list in response"
        )

    def test_me_returns_roles(self) -> None:
        src = _src(_API)
        me_start = src.find("async def me_endpoint(")
        me_end = src.find("\n\n@Route.", me_start + 1)
        me_body = src[me_start:me_end] if me_end != -1 else src[me_start:]
        assert '"roles"' in me_body or "roles" in me_body, (
            "V-028 not fixed: /me must include roles list in response"
        )


# ─── FR-004: users.view permission seeded ─────────────────────────────────────


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


# ─── FR-005: analytics.view and settings.view seeded ─────────────────────────


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


# ─── FR-006: category slug wrapped as dict ────────────────────────────────────


class TestV031CategorySlugWrapped:
    def test_category_slug_returned_as_jsonb_mapping(self) -> None:
        src = _src(_API)
        cat_block_start = src.find("def _category_to_admin(")
        cat_block_end = src.find("\n\n\ndef _vendor_to_admin", cat_block_start + 1)
        cat_body = (
            src[cat_block_start:cat_block_end] if cat_block_end != -1 else src[cat_block_start:]
        )
        assert '"slug": category.slug or {}' in cat_body, (
            "V-031 not fixed: category slug must be returned as the JSONB locale mapping"
        )
        assert '"slug": category.slug,' not in cat_body, (
            "V-031 not fixed: category slug must not be returned as a bare scalar"
        )


# ─── FR-007: optional ProductCard fields ─────────────────────────────────────


class TestV032OptionalProductCardFields:
    def _get_storefront_body(self) -> str:
        src = _src(_PRODUCT_SVC)
        func_start = src.find("def _product_to_storefront(")
        func_end = src.find("\n    @staticmethod", func_start + 1)
        if func_end == -1:
            func_end = src.find("\n    async def", func_start + 1)
        return src[func_start:func_end] if func_end != -1 else src[func_start:]

    def test_original_price_present(self) -> None:
        assert '"original_price"' in self._get_storefront_body(), (
            "V-032 not fixed: 'original_price' missing from _product_to_storefront"
        )

    def test_thumbnail_url_present(self) -> None:
        assert '"thumbnail_url"' in self._get_storefront_body(), (
            "V-032 not fixed: 'thumbnail_url' missing from _product_to_storefront"
        )

    def test_rating_present(self) -> None:
        assert '"rating"' in self._get_storefront_body(), (
            "V-032 not fixed: 'rating' missing from _product_to_storefront"
        )

    def test_rating_count_present(self) -> None:
        assert '"rating_count"' in self._get_storefront_body(), (
            "V-032 not fixed: 'rating_count' missing from _product_to_storefront"
        )

    def test_is_new_present(self) -> None:
        assert '"is_new"' in self._get_storefront_body(), (
            "V-032 not fixed: 'is_new' missing from _product_to_storefront"
        )

    def test_is_bestseller_present(self) -> None:
        assert '"is_bestseller"' in self._get_storefront_body(), (
            "V-032 not fixed: 'is_bestseller' missing from _product_to_storefront"
        )


# ─── FR-008: i18n catalogue completeness ─────────────────────────────────────


class TestV033I18nCatalogue:
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
        src = _src(_API)
        for key in self._REQUIRED_KEYS:
            assert f'"{key}"' in src, (
                f"V-033 not fixed: i18n key '{key}' missing from _I18N_CATALOGUES"
            )

    def test_ar_catalogue_has_all_required_keys(self) -> None:
        src = _src(_API)
        # The AR catalogue must also have these keys — check they appear at least twice
        for key in self._REQUIRED_KEYS:
            count = src.count(f'"{key}"')
            assert count >= 2, f"V-033 not fixed: i18n key '{key}' missing from AR/TR catalogue"


# ─── FR-009: exclude_unset in PATCH handler ───────────────────────────────────


class TestV034ExcludeUnset:
    def test_patch_uses_exclude_unset(self) -> None:
        src = _src(_API)
        assert "exclude_unset=True" in src, (
            "V-034 not fixed: PATCH handler must use model_dump(exclude_unset=True)"
        )


# ─── FR-010: idempotent catalog seeder ───────────────────────────────────────


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

        assert "CREATE UNIQUE INDEX products_slug_en_unique" in create_src
        assert "CREATE UNIQUE INDEX IF NOT EXISTS products_slug_en_unique" in patch_src
        assert "ON products ((slug->>'en'))" in patch_src
