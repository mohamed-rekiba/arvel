"""Create the ``products`` table (UUID v7 PK, JSONB i18n, FTS tsvector)."""

from __future__ import annotations

from arvel.database import Blueprint, Schema
from arvel.database.schema import IdType

__tablename__ = "products"

_CREATE_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION products_search_vector_update() RETURNS trigger AS $$
BEGIN
  NEW.search_vector :=
    setweight(to_tsvector('simple',
      coalesce(NEW.name->>'en', '') || ' ' ||
      coalesce(NEW.name->>'ar', '') || ' ' ||
      coalesce(NEW.name->>'tr', '')
    ), 'A') ||
    setweight(to_tsvector('simple',
      coalesce(NEW.description->>'en', '') || ' ' ||
      coalesce(NEW.description->>'ar', '') || ' ' ||
      coalesce(NEW.description->>'tr', '')
    ), 'B');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""

_CREATE_TRIGGER_SQL = """
CREATE TRIGGER products_search_vector_update
BEFORE INSERT OR UPDATE ON products
FOR EACH ROW EXECUTE FUNCTION products_search_vector_update()
"""

_DROP_TRIGGER_SQL = "DROP TRIGGER IF EXISTS products_search_vector_update ON products"
_DROP_FUNCTION_SQL = "DROP FUNCTION IF EXISTS products_search_vector_update()"


async def up(schema: Schema) -> None:
    def _table(t: Blueprint) -> None:
        t.id(id_type=IdType.UUID)
        t.jsonb("name")
        t.jsonb("slug")
        t.jsonb("description")
        t.decimal("price", precision=10, scale=2).nullable(value=False)
        t.integer("stock_qty").default(0).nullable(value=False)
        t.enum("status", values=["draft", "published"]).default("draft").nullable(value=False)
        t.datetime("published_at").nullable()
        # UUID FKs to categories and vendors
        t.uuid("category_id").nullable().constrained("categories")
        t.uuid("vendor_id").nullable().constrained("vendors")
        t.tsvector("search_vector").nullable()
        t.timestamps()
        t.soft_deletes()
        t.gin_index("products", "search_vector")
        t.gin_index("products", "name")
        t.gin_index("products", "slug")
        t.gin_index("products", "description")
        t.index(
            ["status", "deleted_at"],
            name="products_status_deleted_at_idx",
            where="deleted_at IS NULL",
        )
        t.index(["category_id"], name="products_category_id_idx")
        t.index(["vendor_id"], name="products_vendor_id_idx")
        t.expression_index("(slug->>'en')", name="products_slug_en_unique", unique=True)

    schema.create(__tablename__, _table)
    schema.run_sql(_CREATE_FUNCTION_SQL)
    schema.run_sql(_CREATE_TRIGGER_SQL)


async def down(schema: Schema) -> None:
    schema.run_sql(_DROP_TRIGGER_SQL)
    schema.run_sql(_DROP_FUNCTION_SQL)
    schema.drop_if_exists(__tablename__)
    schema.run_sql("DROP TYPE IF EXISTS products_status")
