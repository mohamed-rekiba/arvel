"""Create the ``products_catalog`` materialized view.

This view covers ALL non-deleted products and adds a ``real_status`` column
so both the storefront and the admin can query it with a single scan.

Storefront: WHERE real_status = 'visible'
Admin:      full table — filter by status / real_status as needed

``real_status`` values (evaluated in priority order):
  'draft'             — product.status = 'draft'
  'not_scheduled'     — status='published' but published_at IS NULL
  'scheduled'         — status='published' but published_at > NOW() (future)
  'category_deleted'  — any ancestor category is soft-deleted
  'category_hidden'   — any ancestor is unpublished or not yet scheduled
  'vendor_deleted'    — linked vendor is soft-deleted
  'vendor_hidden'     — linked vendor is unpublished or not yet scheduled
  'visible'           — fully storefront-ready

Refresh strategy:
1. On mutation — product/category/vendor writes fire the observer, which
   calls refresh_products_catalog() after the transaction commits.
2. Every 10 minutes — scheduler job with a Redis lock (prevents concurrent runs).
3. Admin on-demand — POST /api/admin/products/catalog/refresh.

CONCURRENTLY requires a unique index — ``idx_products_catalog_id_unique``.
"""

from __future__ import annotations

from arvel.database import Schema

__viewname__ = "products_catalog"

_SELECT_SQL = """
    WITH RECURSIVE _cat_chain AS (
        SELECT
            id          AS leaf_id,
            id,
            parent_id,
            status,
            deleted_at,
            published_at
        FROM categories
        UNION ALL
        SELECT
            ch.leaf_id,
            c.id,
            c.parent_id,
            c.status,
            c.deleted_at,
            c.published_at
        FROM _cat_chain ch
        JOIN categories c ON c.id = ch.parent_id
    ),
    _cat_issues AS (
        -- For each leaf category, capture the worst problem anywhere in
        -- its ancestry chain (the leaf itself included).
        SELECT
            leaf_id AS category_id,
            bool_or(deleted_at IS NOT NULL)
                AS has_deleted,
            bool_or(
                deleted_at IS NULL
                AND (status != 'published' OR published_at IS NULL OR published_at > NOW())
            ) AS has_hidden
        FROM _cat_chain
        GROUP BY leaf_id
    )
    SELECT
        p.id,
        p.name,
        p.slug,
        p.description,
        p.price,
        p.stock_qty,
        p.status,
        p.published_at,
        p.search_vector,
        p.created_at,
        p.updated_at,
        p.category_id,
        c.name       AS category_name,
        c.slug       AS category_slug,
        c.parent_id  AS category_parent_id,
        pc.name      AS parent_category_name,
        pc.slug      AS parent_category_slug,
        p.vendor_id,
        v.name       AS vendor_name,
        v.slug       AS vendor_slug,
        CASE
            WHEN p.status = 'draft'
                THEN 'draft'
            WHEN p.published_at IS NULL
                THEN 'not_scheduled'
            WHEN p.published_at > NOW()
                THEN 'scheduled'
            WHEN p.category_id IS NOT NULL AND ci.has_deleted
                THEN 'category_deleted'
            WHEN p.category_id IS NOT NULL AND ci.has_hidden
                THEN 'category_hidden'
            WHEN p.vendor_id IS NOT NULL AND v.deleted_at IS NOT NULL
                THEN 'vendor_deleted'
            WHEN p.vendor_id IS NOT NULL
                AND (v.status != 'published' OR v.published_at IS NULL OR v.published_at > NOW())
                THEN 'vendor_hidden'
            ELSE 'visible'
        END          AS real_status
    FROM products p
    LEFT JOIN _cat_issues ci ON ci.category_id = p.category_id
    LEFT JOIN categories c   ON c.id = p.category_id
    LEFT JOIN categories pc  ON pc.id = c.parent_id
    LEFT JOIN vendors v      ON v.id = p.vendor_id
    WHERE p.deleted_at IS NULL
"""

_REFRESH_FN_SQL = """
CREATE OR REPLACE FUNCTION refresh_products_catalog()
RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE
    cnt bigint;
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY products_catalog;
    SELECT COUNT(*) INTO cnt FROM products_catalog;
    RETURN cnt;
END;
$$
"""


async def up(schema: Schema) -> None:
    # WITH NO DATA — the initial refresh runs separately after seeding to avoid
    # a long lock during migration on a populated database.
    schema.create_materialized_view(__viewname__, _SELECT_SQL, with_data=False)
    # Required for REFRESH MATERIALIZED VIEW CONCURRENTLY.
    schema.create_index("idx_products_catalog_id_unique", __viewname__, ["id"], unique=True)
    schema.create_index(
        "idx_products_catalog_search_gin", __viewname__, ["search_vector"], using="gin"
    )
    schema.create_index("idx_products_catalog_category_id", __viewname__, ["category_id"])
    schema.create_index(
        "idx_products_catalog_category_parent_id", __viewname__, ["category_parent_id"]
    )
    schema.create_index("idx_products_catalog_vendor_id", __viewname__, ["vendor_id"])
    schema.create_index("idx_products_catalog_price", __viewname__, ["price"])
    schema.create_expression_index(
        "idx_products_catalog_published_at", __viewname__, "published_at DESC"
    )
    schema.create_index("idx_products_catalog_real_status", __viewname__, ["real_status"])
    schema.run_sql(_REFRESH_FN_SQL)
    schema.refresh_materialized_view(__viewname__, concurrently=False)


async def down(schema: Schema) -> None:
    schema.run_sql("DROP FUNCTION IF EXISTS refresh_products_catalog()")
    schema.drop_materialized_view_if_exists(__viewname__)
