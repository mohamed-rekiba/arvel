# ADR-070: has-one-of-many (latest/oldest/of_many)

Status: Accepted (delivered WI-arvel-030)

Epic 007 Story 5. Adds Laravel's `latestOfMany` / `oldestOfMany` / `ofMany` — pick exactly one
related row per owner, the winner of MAX (latest) or MIN (oldest) of a column. Two surfaces, because
the parity examples use both.

## ADR-070-01: Method style off `has_many` / `has_one`

Status: Accepted

`HasMany` and `HasOne` now share an `_OfMany` base with three coroutines:

```python
latest = await post.has_many(Comment).latest_of_many("created_at")
oldest = await post.has_many(Comment).oldest_of_many("created_at")
row    = await post.has_many(Comment).of_many("score", aggregate="max")
```

They order by the column (desc for max, asc for min) with the **PK as a deterministic tiebreaker**,
then take the first row. This is the per-instance, lazy form — no new relation type, just sugar over
the existing FK-scoped query builder.

## ADR-070-02: Descriptor style for eager loading (`HasOneOfMany`)

Status: Accepted

`has_many`/`has_one` are method-style and don't participate in `with_()`. To eager-load one-of-many
over a list, `HasOneOfMany` is a descriptor (like `MorphOne`):

```python
class Post(Model):
    latest_comment: ClassVar[HasOneOfMany[Comment]] = HasOneOfMany(
        Comment, column="created_at", aggregate="max"
    )
```

`foreign_key` defaults to `{snake(owner)}_{local_key}`. The lazy accessor (`await post.latest_comment`)
runs the same ordered `LIMIT 1` as the method form.

## ADR-070-03: Batched eager loading via a grouped subquery

Status: Accepted

`_resolve_relation` recognises `HasOneOfMany` and returns a `one_of_many` target with a
`HasOneOfManyLink`. `with_("latest_comment")` routes through the async eager engine and
`batch_load_one_of_many` runs **one** grouped subquery instead of every related row:

```sql
SELECT related.* FROM related
JOIN (SELECT fk, MAX(col) AS agg FROM related WHERE fk IN (:pks) GROUP BY fk) t
  ON related.fk = t.fk AND related.col = t.agg
```

Ties (two rows sharing the aggregate value) are resolved in Python by keeping the larger PK, so each
owner gets exactly one winner. Results land in the per-instance eager cache, so the accessor read is
N+1-free (verified by a SELECT counter: posts + one subquery = 2). Nested paths
(`latest_comment.author`) recurse through the normal loader.

## ADR-070-04: Query-builder complexity refactor

Status: Accepted

The extra relation kind pushed `_resolve_relation` and `_load_async_relation_path` past the
complexity/return-count gates, so both were split into dispatchers over focused helpers
(`_resolve_descriptor_relation` / `_resolve_morph_descriptor`, and `_load_morph_to_path` /
`_load_morph_child_path` / `_load_one_of_many_path`). Behaviour is unchanged.
