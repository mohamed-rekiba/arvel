"""Unit tests for serialization, model, and behavioral fixes.

Tests use Path.read_text() to inspect source code — no arvel framework import needed.
All tests must FAIL before the fixes are applied and PASS after.
"""

from __future__ import annotations

from pathlib import Path

_BACKEND = Path(__file__).parents[2]
_PRODUCT_SERVICE = _BACKEND / "app" / "services" / "product_service.py"
_PRODUCT_RESOURCE = _BACKEND / "app" / "http" / "resources" / "product_resource.py"
_PUBLISHED_PRODUCT = _BACKEND / "app" / "models" / "product_catalog.py"
_ROUTES = _BACKEND / "routes" / "api.py"
_CART_SERVICE = _BACKEND / "app" / "services" / "cart_service.py"
_ORDER_SERVICE = _BACKEND / "app" / "services" / "order_service.py"
_MIGRATIONS_INIT = _BACKEND / "database" / "migrations" / "__init__.py"


def _src(path: Path) -> str:
    return path.read_text()


# ─── ProductResource admin datetime serialization ─────────────────────
# The admin product transform lives in the JsonResource (ProductResource), not
# the service — the service is just the call site.


class TestV017ProductAdminDatetimes:
    def test_published_at_isoformat_in_resource(self) -> None:
        src = _src(_PRODUCT_RESOURCE)
        assert "p.published_at.isoformat()" in src, (
            "p.published_at.isoformat() call missing in ProductResource"
        )

    def test_created_at_isoformat_in_resource(self) -> None:
        src = _src(_PRODUCT_RESOURCE)
        assert "p.created_at.isoformat()" in src, (
            "p.created_at.isoformat() call missing in ProductResource"
        )

    def test_updated_at_isoformat_in_resource(self) -> None:
        src = _src(_PRODUCT_RESOURCE)
        assert "p.updated_at.isoformat()" in src, (
            "p.updated_at.isoformat() call missing in ProductResource"
        )

    def test_resource_null_guard_for_timestamps(self) -> None:
        src = _src(_PRODUCT_RESOURCE)
        # Null guards must be present (pattern: field.isoformat() if field else None)
        assert "p.published_at.isoformat() if p.published_at else None" in src, (
            "null guard missing for published_at in ProductResource"
        )
        assert "p.created_at.isoformat() if p.created_at else None" in src, (
            "null guard missing for created_at in ProductResource"
        )
        assert "p.updated_at.isoformat() if p.updated_at else None" in src, (
            "null guard missing for updated_at in ProductResource"
        )


# ─── ProductCatalog model missing columns ────────────────────────────


class TestV018ProductCatalogColumns:
    def test_category_name_column_declared(self) -> None:
        src = _src(_PUBLISHED_PRODUCT)
        assert "category_name" in src, "'category_name' column missing from ProductCatalog"

    def test_category_slug_column_declared(self) -> None:
        src = _src(_PUBLISHED_PRODUCT)
        assert "category_slug" in src, "'category_slug' column missing from ProductCatalog"

    def test_vendor_name_column_declared(self) -> None:
        src = _src(_PUBLISHED_PRODUCT)
        assert "vendor_name" in src, "'vendor_name' column missing from ProductCatalog"

    def test_vendor_slug_column_declared(self) -> None:
        src = _src(_PUBLISHED_PRODUCT)
        assert "vendor_slug" in src, "'vendor_slug' column missing from ProductCatalog"

    def test_description_column_declared(self) -> None:
        src = _src(_PUBLISHED_PRODUCT)
        assert "description" in src, "'description' column missing from ProductCatalog"

    def test_created_at_column_declared(self) -> None:
        src = _src(_PUBLISHED_PRODUCT)
        assert "created_at" in src, "'created_at' column missing from ProductCatalog"

    def test_updated_at_column_declared(self) -> None:
        src = _src(_PUBLISHED_PRODUCT)
        assert "updated_at" in src, "'updated_at' column missing from ProductCatalog"

    def test_all_new_columns_are_mapped(self) -> None:
        src = _src(_PUBLISHED_PRODUCT)
        for col in ("category_name", "category_slug", "vendor_name", "vendor_slug"):
            # After plain annotations are used (no Mapped[T] on left side)
            assert col in src, f"'{col}' column missing from ProductCatalog"


# ─── TOCTOU stock race closed with row lock ───────────────────────────


class TestV019StockRaceGapComment:
    def test_checkout_uses_lock_for_update(self) -> None:
        src = _src(_ORDER_SERVICE)
        assert "lock_for_update()" in src, (
            "checkout does not lock the product row before stock checks"
        )

    def test_g003_gap_comment_removed_after_fix(self) -> None:
        src = _src(_ORDER_SERVICE)
        assert "G-003" not in src, "G-003 framework gap comment remains after row locking shipped"


# ─── Vendor published_at serialization ────────────────────────────────


class TestV020VendorPublishedAt:
    def test_vendor_published_at_uses_isoformat(self) -> None:
        vendor_svc = _BACKEND / "app" / "services" / "vendor_service.py"
        src = _src(vendor_svc)
        assert "vendor.published_at.isoformat()" in src, (
            "vendor.published_at.isoformat() missing in vendor_service.py"
        )

    def test_vendor_published_at_has_null_guard(self) -> None:
        vendor_svc = _BACKEND / "app" / "services" / "vendor_service.py"
        src = _src(vendor_svc)
        assert "vendor.published_at.isoformat() if vendor.published_at else None" in src, (
            "null guard missing for vendor published_at in vendor_service.py"
        )


# ─── Narrow exception handling in register ────────────────────────────


class TestV021RegisterException:
    def test_broad_except_exception_removed_from_register(self) -> None:
        auth_ctrl = _BACKEND / "app" / "http" / "controllers" / "auth.py"
        src = _src(auth_ctrl)
        assert "except Exception" not in src, (
            "broad 'except Exception' still present in auth controller"
        )


# ─── Storefront product exposes category/vendor names ─────────────────


class TestV022StorefrontEnrichedResponse:
    def test_category_name_in_storefront_serializer(self) -> None:
        src = _src(_PRODUCT_SERVICE)
        assert '"category_name"' in src or "'category_name'" in src, (
            "'category_name' not returned in product_to_storefront"
        )

    def test_vendor_name_in_storefront_serializer(self) -> None:
        src = _src(_PRODUCT_SERVICE)
        assert '"vendor_name"' in src or "'vendor_name'" in src, (
            "'vendor_name' not returned in product_to_storefront"
        )


# ─── Missing product raises error in cart ─────────────────────────────


class TestV023CartMissingProduct:
    def test_cart_add_item_guards_missing_product(self) -> None:
        src = _src(_CART_SERVICE)
        # The silent Decimal(0) fallback must be gone
        assert "Decimal(0)" not in src or ("product is None" in src and "raise" in src), (
            "add_item still falls back to Decimal(0) for missing product"
        )

    def test_cart_add_item_raises_on_missing_product(self) -> None:
        src = _src(_CART_SERVICE)
        add_item_idx = src.find("async def add_item")
        assert add_item_idx != -1, "add_item not found in cart_service"
        next_def = src.find("async def ", add_item_idx + 1)
        add_item_body = src[add_item_idx:next_def] if next_def != -1 else src[add_item_idx:]
        assert "raise" in add_item_body, "add_item does not raise when product is missing"


# ─── admin_list_orders / admin_get_order consistency ──────────────────


class TestV024AdminOrderTrashedConsistency:
    def test_admin_list_orders_uses_with_trashed(self) -> None:
        src = _src(_ORDER_SERVICE)
        list_idx = src.find("async def admin_list_orders")
        assert list_idx != -1, "admin_list_orders not found"
        next_def = src.find("async def ", list_idx + 1)
        list_body = src[list_idx:next_def] if next_def != -1 else src[list_idx:]
        assert "with_trashed" in list_body, "admin_list_orders does not use with_trashed()"


# ─── migration sequence gap documented ────────────────────────────────


class TestV025MigrationSequenceGap:
    def test_missing_000004_migration_is_documented(self) -> None:
        src = _src(_MIGRATIONS_INIT)
        assert "000004 is intentionally absent" in src
        assert "Do not create a new 000004 migration" in src
