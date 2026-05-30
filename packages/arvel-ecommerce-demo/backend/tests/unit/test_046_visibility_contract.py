"""Prompt visibility contract tests for the ecommerce materialized view."""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).parents[2]
CATEGORY_MODEL = BASE_DIR / "app" / "models" / "category.py"
VENDOR_MODEL = BASE_DIR / "app" / "models" / "vendor.py"
PRODUCT_CATALOG_MODEL = BASE_DIR / "app" / "models" / "product_catalog.py"
PRODUCT_SERVICE = BASE_DIR / "app" / "services" / "product_service.py"
CATEGORY_MIGRATION = (
    BASE_DIR / "database" / "migrations" / "2026_05_23_000002_create_categories_table.py"
)
VENDOR_MIGRATION = (
    BASE_DIR / "database" / "migrations" / "2026_05_23_000001_create_vendors_table.py"
)
VIEW_MIGRATION = (
    BASE_DIR / "database" / "migrations" / "2026_05_23_000009_create_products_catalog_view.py"
)
CATALOG_SEEDER = BASE_DIR / "database" / "seeders" / "catalog_seeder.py"


def _src(path: Path) -> str:
    return path.read_text()


def test_categories_have_jsonb_slugs_and_publish_fields() -> None:
    migration = _src(CATEGORY_MIGRATION)
    model = _src(CATEGORY_MODEL)

    assert 't.jsonb("slug")' in migration
    assert 't.enum("status", values=["draft", "published"])' in migration
    assert 't.datetime("published_at")' in migration
    assert 't.gin_index("categories", "slug")' in migration
    assert "categories_slug_en_unique" in migration
    assert "slug:" in model
    assert (
        'enum(["draft", "published"]' in model
        or 'enum(["draft","published"]' in model
        or "enum(" in model
    )
    assert "published_at:" in model


def test_vendors_use_published_visibility_status() -> None:
    migration = _src(VENDOR_MIGRATION)
    model = _src(VENDOR_MODEL)
    seeder = _src(CATALOG_SEEDER)

    assert 'values=["draft", "published"]' in migration
    assert '.default("published")' in migration
    assert "enum(" in model, "vendor model should use enum() helper"
    assert 'default="published"' in model
    assert '"status": "published"' in seeder
    assert '"status": "active"' not in seeder


def test_products_catalog_view_covers_all_non_deleted_products() -> None:
    """products_catalog includes all non-deleted products and computes real_status."""
    src = _src(VIEW_MIGRATION)

    # View spans ALL non-deleted products.
    assert "WHERE p.deleted_at IS NULL" in src
    # real_status CASE expression covers every visibility condition.
    assert "real_status" in src
    assert "'visible'" in src
    assert "THEN 'draft'" in src
    # Category chain checks — evaluated via CTE aggregation.
    assert "deleted_at IS NOT NULL" in src
    assert "status != 'published'" in src
    assert "published_at > NOW()" in src
    # Vendor checks.
    assert "v.deleted_at IS NOT NULL" in src
    assert "v.status != 'published'" in src
    # Storefront constraint is v.status = 'active' is forbidden.
    assert "v.status = 'active'" not in src
    # DB refresh function is registered.
    assert "refresh_products_catalog()" in src


def test_storefront_filters_by_real_status_visible() -> None:
    """Storefront queries must use real_status = 'visible' instead of raw WHERE clauses."""
    service = _src(PRODUCT_SERVICE)
    assert 'real_status == "visible"' in service or "real_status = 'visible'" in service


def test_storefront_serializes_locale_aware_category_fields() -> None:
    model = _src(PRODUCT_CATALOG_MODEL)
    service = _src(PRODUCT_SERVICE)

    assert "category_name:" in model
    assert "category_slug:" in model
    assert 'where_json_path("slug", locale, slug)' in service
    assert '"slug": TranslatableMixin.translate_dict(slug_data, locale)' in service
    assert (
        '"category_name": TranslatableMixin.translate_dict(category_name_data, locale)' in service
    )
    assert (
        '"category_slug": TranslatableMixin.translate_dict(category_slug_data, locale)' in service
    )


def test_products_gin_indexes_cover_all_translation_columns() -> None:
    src = _src(BASE_DIR / "database" / "migrations" / "2026_05_23_000003_create_products_table.py")

    for column in ("name", "slug", "description"):
        assert f't.gin_index("products", "{column}")' in src
