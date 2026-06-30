# JSON, Full-text & Vectors

Query special column types in SQL — JSON/JSONB documents, Postgres full-text search, and
pgvector embeddings — without pulling rows into Python first.

## Querying JSON columns

A `json`/`jsonb` column holds structured data — settings, metadata, tags. You don't have to pull
the whole document into Python to filter on a value inside it; query the JSON in SQL directly.

Use `where_json(column, path, value)` to match a value at a key or nested path. The `path` is a key
(`"lang"`), a nested path (`"meta->v"` or the equivalent `"meta.v"`), or an array index
(`"tags->0"`). It compiles to `json_extract` on SQLite and `->>` on Postgres, so the same query
runs on both:

```python
# users whose settings JSON has {"notifications": {"email": "on"}}
await User.where_json("settings", "notifications->email", "on").get()
```

For Postgres `jsonb` *containment* — "does this column contain this fragment?" — use
`where_json_contains(column, value)`, which emits the `@>` operator:

```python
# documents whose data->tags array contains "release"
await Document.where_json_contains("data", ["release"]).get()
```

!!! tip "Index it with GIN"
    A `jsonb` column you filter often should be backed by a **GIN index** so containment and key
    lookups stay fast. Declare it in the migration blueprint:

    ```python
    t.jsonb("data")
    t.gin_index("data")        # USING gin on Postgres; a plain index on SQLite
    ```

    `t.gist_index(...)` is the GiST counterpart (geometric/range types and `tsvector`). Both emit
    the Postgres access method on Postgres and degrade to a plain index on other dialects.

    For an **exact key lookup** in a `jsonb` column (e.g. a per-locale i18n field you filter or sort
    by), a B-tree **expression index** is the better fit than GIN — `t.btree_index` takes a raw
    expression:

    ```python
    t.btree_index("name->>'en'")   # CREATE INDEX ... ((name->>'en'))  — fast WHERE/ORDER BY name->>'en'
    ```

    Rule of thumb: **GIN** for "does this jsonb *contain* X / have key K" (`@>`, `?`); **btree
    expression** for "this jsonb's value at a known key equals/sorts". `t.btree_index` also takes
    multiple columns for a composite index.

!!! warning "Compare as text"
    `where_json` compares the extracted value **as text**, so pass the value as a string
    (`"2"`, not `2`). This keeps the operator portable across SQLite and Postgres.

## Full-text search

For natural-language search over a text column — "find articles about *fast async python*",
ranked by relevance, ignoring stop-words and matching word stems — Postgres has built-in
full-text search. `where_fulltext(column, query)` runs it:

```python
# articles whose body matches the natural-language query
await Article.where_fulltext("body", "fast async python").get()
```

It compiles to `to_tsvector('english', body) @@ plainto_tsquery('english', :query)`. Pass
`language=` for another configuration (`where_fulltext("corps", q, language="french")`).

For a large, frequently-searched table, store a **precomputed `tsvector` column** and back it with
a GIN index instead of tokenising on every query:

```python
t.tsvector("search")          # a TSVECTOR column on Postgres (Text elsewhere)
t.gin_index("search")         # makes @@ matches fast
```

!!! note "Postgres feature"
    `where_fulltext` targets Postgres — build the query on a Postgres connection. On SQLite the
    `tsvector` column degrades to `Text` so migrations still run, but the `@@` match operator is
    Postgres-only.


## Vector columns (pgvector)

Store embeddings in a `vector` column for semantic search. It maps to a real pgvector column when
the `[vector]` extra is installed (and the server has `CREATE EXTENSION vector;`), and falls back
to a portable JSON column otherwise:

```python
t.vector("embedding", dimensions=1536)        # in a migration blueprint
```

Nearest-neighbour search uses pgvector's distance operators (`<->` L2, `<=>` cosine). Compute the
distance with `select_raw` and order by it:

```python
hits = await (Document.query()
    .select_raw(f"*, embedding <=> '{q}' AS distance")   # q: the query embedding literal
    .order_by("distance")
    .limit(5)
    .get())
```
