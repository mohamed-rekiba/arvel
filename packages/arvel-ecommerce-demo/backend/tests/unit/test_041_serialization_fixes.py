"""Unit tests for WI-arvel-041: serialization, model, and behavioral fixes.

Tests use Path.read_text() to inspect source code — no arvel framework import needed.
All tests must FAIL before the fixes are applied and PASS after.
"""

from __future__ import annotations

from pathlib import Path

_BACKEND = Path(__file__).parents[2]
_PRODUCT_SERVICE = _BACKEND / "app" / "services" / "product_service.py"
_PUBLISHED_PRODUCT = _BACKEND / "app" / "models" / "product_catalog.py"
_ROUTES = _BACKEND / "routes" / "api.py"
_CART_SERVICE = _BACKEND / "app" / "services" / "cart_service.py"
_ORDER_SERVICE = _BACKEND / "app" / "services" / "order_service.py"
_MIGRATIONS_INIT = _BACKEND / "database" / "migrations" / "__init__.py"


def _src(path: Path) -> str:
    return path.read_text()


# ─── V-017: _product_to_admin datetime serialization ─────────────────────────


class TestV017ProductAdminDatetimes:
    def test_published_at_isoformat_in_product_to_admin(self) -> None:
        src = _src(_PRODUCT_SERVICE)
        assert "product.published_at.isoformat()" in src, (
            "V-017 not fixed: product.published_at.isoformat() call missing in _product_to_admin"
        )

    def test_created_at_isoformat_in_product_to_admin(self) -> None:
        src = _src(_PRODUCT_SERVICE)
        assert "product.created_at.isoformat()" in src, (
            "V-017 not fixed: product.created_at.isoformat() call missing in _product_to_admin"
        )

    def test_updated_at_isoformat_in_product_to_admin(self) -> None:
        src = _src(_PRODUCT_SERVICE)
        assert "product.updated_at.isoformat()" in src, (
            "V-017 not fixed: product.updated_at.isoformat() call missing in _product_to_admin"
        )

    def test_product_to_admin_null_guard_for_timestamps(self) -> None:
        src = _src(_PRODUCT_SERVICE)
        # Null guards must be present (pattern: field.isoformat() if field else None)
        assert "product.published_at.isoformat() if product.published_at else None" in src, (
            "V-017 not fixed: null guard missing for published_at in _product_to_admin"
        )
        assert "product.created_at.isoformat() if product.created_at else None" in src, (
            "V-017 not fixed: null guard missing for created_at in _product_to_admin"
        )
        assert "product.updated_at.isoformat() if product.updated_at else None" in src, (
            "V-017 not fixed: null guard missing for updated_at in _product_to_admin"
        )


# ─── V-018: ProductCatalog model missing columns ────────────────────────────


class TestV018ProductCatalogColumns:
    def test_category_name_column_declared(self) -> None:
        src = _src(_PUBLISHED_PRODUCT)
        assert "category_name" in src, (
            "V-018 not fixed: 'category_name' column missing from ProductCatalog"
        )

    def test_category_slug_column_declared(self) -> None:
        src = _src(_PUBLISHED_PRODUCT)
        assert "category_slug" in src, (
            "V-018 not fixed: 'category_slug' column missing from ProductCatalog"
        )

    def test_vendor_name_column_declared(self) -> None:
        src = _src(_PUBLISHED_PRODUCT)
        assert "vendor_name" in src, (
            "V-018 not fixed: 'vendor_name' column missing from ProductCatalog"
        )

    def test_vendor_slug_column_declared(self) -> None:
        src = _src(_PUBLISHED_PRODUCT)
        assert "vendor_slug" in src, (
            "V-018 not fixed: 'vendor_slug' column missing from ProductCatalog"
        )

    def test_description_column_declared(self) -> None:
        src = _src(_PUBLISHED_PRODUCT)
        assert "description" in src, (
            "V-018 not fixed: 'description' column missing from ProductCatalog"
        )

    def test_created_at_column_declared(self) -> None:
        src = _src(_PUBLISHED_PRODUCT)
        assert "created_at" in src, (
            "V-018 not fixed: 'created_at' column missing from ProductCatalog"
        )

    def test_updated_at_column_declared(self) -> None:
        src = _src(_PUBLISHED_PRODUCT)
        assert "updated_at" in src, (
            "V-018 not fixed: 'updated_at' column missing from ProductCatalog"
        )

    def test_all_new_columns_are_mapped(self) -> None:
        src = _src(_PUBLISHED_PRODUCT)
        for col in ("category_name", "category_slug", "vendor_name", "vendor_slug"):
            # After WI-arvel-010, plain annotations are used (no Mapped[T] on left side)
            assert col in src, f"V-018 not fixed: '{col}' column missing from ProductCatalog"


# ─── V-019: TOCTOU stock race closed with row lock ───────────────────────────


class TestV019StockRaceGapComment:
    def test_checkout_uses_lock_for_update(self) -> None:
        src = _src(_ORDER_SERVICE)
        assert "lock_for_update()" in src, (
            "V-019 not fixed: checkout does not lock the product row before stock checks"
        )

    def test_g003_gap_comment_removed_after_fix(self) -> None:
        src = _src(_ORDER_SERVICE)
        assert "G-003" not in src, (
            "V-019 stale: G-003 framework gap comment remains after row locking shipped"
        )


# ─── V-020: Vendor published_at serialization ────────────────────────────────


class TestV020VendorPublishedAt:
    def test_vendor_published_at_uses_isoformat(self) -> None:
        src = _src(_ROUTES)
        assert "vendor.published_at.isoformat()" in src, (
            "V-020 not fixed: vendor.published_at.isoformat() missing in vendor serializer"
        )

    def test_vendor_published_at_has_null_guard(self) -> None:
        src = _src(_ROUTES)
        assert "vendor.published_at.isoformat() if vendor.published_at else None" in src, (
            "V-020 not fixed: null guard missing for vendor published_at in api.py"
        )


# ─── V-021: Narrow exception handling in register ────────────────────────────


class TestV021RegisterException:
    def test_broad_except_exception_removed_from_register(self) -> None:
        src = _src(_ROUTES)
        # Find the register endpoint section and check there's no bare `except Exception`
        # We check that the broad catch is gone from the register body
        register_idx = src.find("async def register_endpoint")
        assert register_idx != -1, "register_endpoint not found"
        # Extract a window after the function definition (up to the next route decorator)
        next_route = src.find("@Route.", register_idx + 1)
        register_body = src[register_idx:next_route] if next_route != -1 else src[register_idx:]
        assert "except Exception" not in register_body, (
            "V-021 not fixed: broad 'except Exception' still present in register_endpoint"
        )


# ─── V-022: Storefront product exposes category/vendor names ─────────────────


class TestV022StorefrontEnrichedResponse:
    def test_category_name_in_storefront_serializer(self) -> None:
        src = _src(_PRODUCT_SERVICE)
        assert '"category_name"' in src or "'category_name'" in src, (
            "V-022 not fixed: 'category_name' not returned in _product_to_storefront"
        )

    def test_vendor_name_in_storefront_serializer(self) -> None:
        src = _src(_PRODUCT_SERVICE)
        assert '"vendor_name"' in src or "'vendor_name'" in src, (
            "V-022 not fixed: 'vendor_name' not returned in _product_to_storefront"
        )


# ─── V-023: Missing product raises error in cart ─────────────────────────────


class TestV023CartMissingProduct:
    def test_cart_add_item_guards_missing_product(self) -> None:
        src = _src(_CART_SERVICE)
        # The silent Decimal(0) fallback must be gone
        assert "Decimal(0)" not in src or ("product is None" in src and "raise" in src), (
            "V-023 not fixed: add_item still falls back to Decimal(0) for missing product"
        )

    def test_cart_add_item_raises_on_missing_product(self) -> None:
        src = _src(_CART_SERVICE)
        add_item_idx = src.find("async def add_item")
        assert add_item_idx != -1, "add_item not found in cart_service"
        next_def = src.find("async def ", add_item_idx + 1)
        add_item_body = src[add_item_idx:next_def] if next_def != -1 else src[add_item_idx:]
        assert "raise" in add_item_body, (
            "V-023 not fixed: add_item does not raise when product is missing"
        )


# ─── V-024: admin_list_orders / admin_get_order consistency ──────────────────


class TestV024AdminOrderTrashedConsistency:
    def test_admin_list_orders_uses_with_trashed(self) -> None:
        src = _src(_ORDER_SERVICE)
        list_idx = src.find("async def admin_list_orders")
        assert list_idx != -1, "admin_list_orders not found"
        next_def = src.find("async def ", list_idx + 1)
        list_body = src[list_idx:next_def] if next_def != -1 else src[list_idx:]
        assert "with_trashed" in list_body, (
            "V-024 not fixed: admin_list_orders does not use with_trashed()"
        )


# ─── V-025: migration sequence gap documented ────────────────────────────────


class TestV025MigrationSequenceGap:
    def test_missing_000004_migration_is_documented(self) -> None:
        src = _src(_MIGRATIONS_INIT)
        assert "000004 is intentionally absent" in src
        assert "Do not create a new 000004 migration" in src
