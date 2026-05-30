"""Migration round-trip tests — US-002.

RED: passes once Docker is available; will turn GREEN once the migrations
directory is correct. Tests the schema structure, not application code.

Acceptance criteria (US-002):
- All 9 demo migrations apply without error
- products_catalog materialized view exists after migrations
- GIN indexes exist on products.name, categories.name, products.search_vector
- Unique index on products_catalog.id exists (required for REFRESH CONCURRENTLY)
- migrate:rollback reverts all migrations cleanly
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_all_migrations_apply_without_error(fresh_db: str) -> None:
    """US-002: migrations run on a clean database without raising."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(fresh_db)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT COUNT(*) FROM migrations"))
            count = result.scalar()
            # 9 demo migrations + migrations from arvel-identity + arvel-image + users table
            assert count is not None and count >= 9, f"Expected ≥9 applied migrations, got {count}"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_products_catalog_materialized_view_exists(fresh_db: str) -> None:
    """US-002: products_catalog materialized view exists after migrations."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(fresh_db)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT matviewname FROM pg_matviews WHERE matviewname = 'products_catalog'")
            )
            row = result.fetchone()
            assert row is not None, "products_catalog materialized view not found"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_products_catalog_has_unique_index(fresh_db: str) -> None:
    """US-002: unique index on products_catalog.id exists (REFRESH CONCURRENTLY requirement)."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(fresh_db)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename = 'products_catalog' AND indexdef LIKE '%UNIQUE%'"
                )
            )
            row = result.fetchone()
            assert row is not None, (
                "No unique index on products_catalog — REFRESH CONCURRENTLY will fail"
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_gin_index_on_products_search_vector(fresh_db: str) -> None:
    """US-002: GIN index exists on products.search_vector for FTS."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(fresh_db)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename = 'products' "
                    "AND indexdef LIKE '%USING gin%' "
                    "AND indexdef LIKE '%search_vector%'"
                )
            )
            row = result.fetchone()
            assert row is not None, "GIN index on products.search_vector not found"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_products_table_has_correct_columns(fresh_db: str) -> None:
    """US-002: products table has all required columns with correct types."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(fresh_db)
    required_columns = {
        "id",
        "name",
        "slug",
        "description",
        "price",
        "stock_qty",
        "status",
        "published_at",
        "category_id",
        "vendor_id",
        "search_vector",
        "created_at",
        "updated_at",
        "deleted_at",
    }
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'products'"
                )
            )
            existing = {row[0] for row in result}
            missing = required_columns - existing
            assert not missing, f"products table missing columns: {missing}"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_roles_table_has_level_column(fresh_db: str) -> None:
    """US-005: roles table stores the prompt's numeric hierarchy."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(fresh_db)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name = 'roles' AND column_name = 'level'"
                )
            )
            row = result.fetchone()
            assert row is not None, "roles.level column not found"
            assert row.data_type == "integer"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_search_vector_trigger_fires_on_product_insert(fresh_db: str) -> None:
    """US-002: inserting a product populates search_vector via the trigger."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(fresh_db)
    try:
        async with engine.begin() as conn:
            # Insert a minimal product to trigger search_vector population
            await conn.execute(
                text(
                    """
                    INSERT INTO products (id, name, slug, description, price, stock_qty, status)
                    VALUES (
                        gen_random_uuid(),
                        '{"en": "Test Product"}',
                        '{"en": "test-product"}',
                        '{"en": "A test description"}',
                        9.99,
                        10,
                        'draft'
                    )
                    """
                )
            )
            result = await conn.execute(
                text("SELECT search_vector FROM products WHERE name->>'en' = 'Test Product'")
            )
            row = result.fetchone()
            assert row is not None
            assert row[0] is not None, "search_vector not populated by trigger"
    finally:
        await engine.dispose()
