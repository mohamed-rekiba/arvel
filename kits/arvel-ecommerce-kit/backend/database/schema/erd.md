# Entity-Relationship Diagram

## Tables

### Core identity (from arvel-starter / arvel-identity)

```
users               id (uuid, PK), name, email (unique), password, locale, theme,
                    suspended_at, remember_token, timestamps(), soft_deletes()

roles               id (uuid, PK), name (unique per guard), guard_name, level (INT, added by kit),
                    timestamps()

permissions         id (uuid, PK), name, guard_name, timestamps()

model_has_roles     role_id → roles.id, model_id + model_type + guard_name
model_has_permissions permission_id → permissions.id, model_id + model_type + guard_name
role_has_permissions  role_id → roles.id, permission_id → permissions.id

media               id (uuid, PK), model_type, model_id, collection_name, file_name,
                    mime_type, size, disk (local/s3), path, conversions (json),
                    order_column, timestamps()
```

### E-Commerce (Phase 1)

```
vendors             id (uuid, PK), name (VARCHAR 200), slug (VARCHAR 200, unique),
                    description (TEXT, nullable),
                    status ENUM(draft, published) DEFAULT published,
                    published_at (TIMESTAMP, nullable),
                    timestamps(), soft_deletes()

categories          id (uuid, PK),
                    name (JSONB) {"en": ..., "ar": ..., "tr": ...},
                    slug (JSONB) {"en": ..., "ar": ..., "tr": ...},
                    status ENUM(draft, published) DEFAULT published,
                    published_at (TIMESTAMP, nullable),
                    parent_id → categories.id (nullable, self-referential),
                    timestamps(), soft_deletes()

products            id (uuid, PK),
                    name (JSONB) {"en": ..., "ar": ..., "tr": ...},
                    slug (JSONB) {"en": ..., "ar": ..., "tr": ...},
                    description (JSONB) {"en": ..., "ar": ..., "tr": ...},
                    price (DECIMAL 10,2, NOT NULL),
                    stock_qty (INTEGER, DEFAULT 0, ≥ 0),
                    status ENUM(draft, published) DEFAULT draft,
                    published_at (TIMESTAMP, nullable),
                    category_id → categories.id (NOT NULL, SET NULL cascade on delete),
                    vendor_id → vendors.id (NOT NULL, SET NULL on delete),
                    search_vector (TSVECTOR, nullable, populated by trigger),
                    timestamps(), soft_deletes()

carts               id (uuid, PK),
                    user_id → users.id (unique, CASCADE on delete),
                    timestamps()

cart_items          id (uuid, PK),
                    cart_id → carts.id (CASCADE on delete),
                    product_id → products.id (CASCADE on delete),
                    quantity (INTEGER, ≥ 1),
                    unit_price_snapshot (DECIMAL 10,2),  -- locked at add-to-cart time
                    timestamps()
                    UNIQUE(cart_id, product_id)

orders              id (uuid, PK),
                    user_id → users.id (RESTRICT on delete),
                    status ENUM(pending, confirmed, processing, shipped, delivered, cancelled) DEFAULT pending,
                    total (DECIMAL 10,2, NOT NULL),
                    shipping_address (JSON, NOT NULL),
                    note (TEXT, nullable),
                    timestamps(), soft_deletes()

order_items         id (uuid, PK),
                    order_id → orders.id (CASCADE on delete),
                    product_id → products.id (RESTRICT on delete, nullable — product may be deleted after order),
                    product_name_snapshot (VARCHAR 300, NOT NULL),  -- captured at checkout
                    quantity (INTEGER, ≥ 1),
                    unit_price (DECIMAL 10,2, NOT NULL),
                    subtotal (DECIMAL 10,2, NOT NULL),  -- quantity × unit_price
                    timestamps()
```

### Materialized view

```
published_products  Snapshot joining products × categories (recursive) × vendors.

                    Visibility conditions (all must hold simultaneously):
                      p.status='published', p.deleted_at IS NULL,
                      p.published_at IS NOT NULL AND p.published_at <= NOW()
                      c.status='published', c.deleted_at IS NULL,
                      c.published_at IS NOT NULL AND c.published_at <= NOW()
                      ALL ancestors of c satisfy the same three checks
                        (recursive CTE — any unpublished/deleted ancestor hides the product)
                      v.status='published', v.deleted_at IS NULL,
                      v.published_at IS NOT NULL AND v.published_at <= NOW()

                    Columns: id, name, slug, description, price, stock_qty,
                             published_at, search_vector, created_at, updated_at,
                             category_id, category_name, category_slug,
                             category_parent_id,         -- direct parent ID (nullable)
                             parent_category_name,       -- JSONB, from LEFT JOIN categories pc
                             parent_category_slug,       -- JSONB, from LEFT JOIN categories pc
                             vendor_id, vendor_name, vendor_slug

                    Indexes: UNIQUE(id)                  [required for REFRESH CONCURRENTLY]
                             GIN(search_vector)          [FTS]
                             B-tree(category_id)
                             B-tree(category_parent_id)  [parent-category filter]
                             B-tree(vendor_id)
                             B-tree(price)
                             B-tree DESC(published_at)   [expression index]
```

## Relationships

```
users           ─┬─< orders (1:N via user_id)
                 └─── carts (1:1 via user_id unique)

carts           ─── cart_items (1:N via cart_id)
cart_items      ──> products (N:1 via product_id)

orders          ─── order_items (1:N via order_id)
order_items     ──> products (N:1 via product_id, nullable)

products        ──> categories (N:1 via category_id)
products        ──> vendors (N:1 via vendor_id)
categories      ──> categories (self, parent_id nullable)

products        ─< media (polymorphic via model_type='product', model_id)
vendors         ─< media (polymorphic via model_type='vendor', model_id)

users           ─< model_has_roles (N:M via roles)
users           ─< model_has_permissions (N:M direct permissions)
roles           ─< role_has_permissions (N:M via permissions)
```

## Indexing strategy

| Table | Index type | Columns | Purpose |
|---|---|---|---|
| vendors | B-tree unique | slug | URL lookup |
| vendors | Partial (published) | deleted_at IS NULL | Soft-delete filter |
| categories | B-tree unique | slug->>'en' | URL lookup |
| categories | Partial (published) | deleted_at IS NULL | Soft-delete filter |
| categories | B-tree | parent_id | Child listing |
| products | Partial (active) | deleted_at IS NULL | Soft-delete filter |
| products | B-tree | (status, deleted_at) | Admin list filter |
| products | B-tree | category_id | Category products |
| products | B-tree | vendor_id | Vendor products |
| products | GIN | search_vector | Full-text search |
| products | GIN | name | i18n containment |
| carts | B-tree unique | user_id | One cart per user |
| cart_items | Unique | (cart_id, product_id) | Dedup |
| orders | B-tree | user_id | Customer history |
| orders | B-tree | (status, created_at) | Admin status filter |
| order_items | B-tree | order_id | Order line items |
| published_products | Unique B-tree | id | REFRESH CONCURRENTLY |
| published_products | GIN | search_vector | Storefront FTS |
| published_products | B-tree | category_id | Category filter |
| published_products | B-tree | category_parent_id | Parent-category filter |
| published_products | B-tree | vendor_id | Vendor filter |
| published_products | B-tree | price | Price sort/filter |
| published_products | B-tree DESC (expr) | published_at DESC | Recency sort |
