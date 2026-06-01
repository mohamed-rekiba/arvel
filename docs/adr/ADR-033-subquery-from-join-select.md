# ADR-033: Subquery FROM / JOIN / SELECT

Status: Accepted (delivered WI-arvel-012)

Eloquent-parity increment (backlog `005`, story S3). No HTTP or schema surface —
recorded as an ADR. Builds on the WHERE-predicate engine (ADR-030) and reuses the
existing row-shaping markers in `all()`.

## ADR-033-01: `on` is a callable that receives the aliased subquery

Status: Accepted

Laravel's `joinSub` takes a closure whose `JoinClause` exposes raw column strings. We need
the caller to reference the subquery's columns, but a derived table's columns only exist
once it's aliased. So `join_sub(query, alias, on)` builds the `subquery(alias)` first, then
calls `on(subq)` — the closure receives the alias and references columns the typed way:

```python
SqUser.join_sub(high_value, "hv", lambda hv: hv.c.user_id == SqUser.id)
```

`on` also accepts a bare condition for callers that already hold a reference. `left_join_sub`
is the `kind="left"` shortcut. The join doesn't touch the SELECT list, so results stay model
instances — pull subquery columns in explicitly with `add_select`/`select_sub` when needed.

## ADR-033-02: `from_sub` returns dicts, not model instances

Status: Accepted

`from_sub(query, alias)` replaces the FROM with `select(subq).select_from(subq)` and clears
the inherited WHERE predicate (the outer query operates on the derived table, not the model's
own columns). Because the rows no longer map to the model's mapped entity, `all()` returns
dicts — it reuses the existing `__cols__` marker that already yields `result.mappings()`
dicts. Typed `where()` on derived columns isn't supported; that's raw/derived-column
territory.

## ADR-033-03: `select_sub` / `add_select` append via the `__with_agg__` path

Status: Accepted

`select_sub(query, alias)` turns a single-column sub-builder into a correlated
`scalar_subquery().label(alias)` and appends it with `add_columns`. `add_select(*columns)`
appends model column names (resolved) or raw SQLAlchemy expressions. Both mark the builder
with the existing `__with_agg__` selector, so `all()` keeps the model entity in `row[0]` and
attaches the extra labeled columns onto each instance by name — the same mechanism
`with_count`/`with_sum` already use. This is why appended columns surface as attributes
(`user.top_amount`) rather than forcing a switch to dict rows.
