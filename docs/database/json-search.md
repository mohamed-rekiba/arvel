# JSON, Full-Text & Vectors

Query special column types in SQL — JSON/JSONB documents, Postgres full-text search, and
pgvector embeddings — without pulling rows into Python first.

!!! note "Needs the `[vector]` extra for vector search"
    JSON and Postgres full-text queries ride your existing [database extra](index.md). Vector columns
    and similarity search additionally need pgvector: `uv add 'arvel[vector]'` (plus `CREATE EXTENSION
    vector` on the Postgres server).

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

Similarity queries are first-class on the builder — pass the query embedding as a plain list of
floats (arvel never generates embeddings; bring your own):

```python
# five nearest documents, most similar first (cosine by default)
hits = await Document.query().order_by_similarity("embedding", q).limit(5).get()

# only close matches, composable with ordinary wheres
close = await (Document.query()
    .where("published", True)
    .where_vector_similar("embedding", q, metric="l2", max_distance=0.5)
    .get())
```

`metric` is one of `"cosine"`, `"l2"`, or `"inner"` (negative inner product — ascending is always
most-similar-first). On a column without vector operators (the JSON fallback, or a non-vector
column) both methods raise `UnsupportedDriverOperation` instead of emitting SQL that would compare
strings.

## Common mistakes & gotchas

- **Expecting vectors off Postgres.** Similarity search needs pgvector — on a column without vector
  operators it raises `UnsupportedDriverOperation` rather than silently doing something wrong.
- **Generating embeddings inside arvel.** It doesn't — you bring your own vector (a plain list of
  floats) from whatever model you use, and arvel only does the SQL-side nearest-neighbour query.
- **Full-text on SQLite.** Postgres full-text operators are Postgres-only; check `db` dialect (or the
  degradation warning) before relying on them in a cross-backend migration.
- **JSON path typos.** A JSON path that doesn't match returns no rows rather than erroring — verify
  the path against a sample document.

## See also

- [Queries](queries.md) — the builder these JSON/full-text/vector methods extend.
- [SQL Views & Functions](sql-views.md) — the GIN/GiST indexes and extensions these queries want.
- [Casts & Serialization](casts.md) — the `json`/`array` casts for reading JSON columns into Python.
- [Search](../search.md) — application-level search indexing, distinct from in-database full-text.
