# ORM Best Practices

Patterns and anti-patterns for models, repositories, queries, relationships, transactions, and async session usage in Arvel's data layer.

---

## Model Design

### Use `Mapped[T]` + `mapped_column()`

```python
# Correct — SA 2.0 typed columns
id: Mapped[int] = mapped_column(primary_key=True)
name: Mapped[str] = mapped_column(String(255))
bio: Mapped[str | None]
is_active: Mapped[bool] = mapped_column(default=True)
```

Reserve `Column()` for Core-layer usage only (pivot tables, raw SQL construction).

### Naming Conventions

| Convention | Rule | Example |
|-----------|------|---------|
| Table names | Plural snake_case | `users`, `blog_posts`, `order_items` |
| `__tablename__` | Always set explicitly | `__tablename__ = "users"` |
| FK columns | `{related_singular}_id` | `user_id`, `post_id` |
| Irregular plurals | Set `__singular__` | `__singular__ = "person"` for `people` table |
| Pivot tables | Alphabetical singular join | `role_user`, `post_tag` |

### Mass Assignment

Always declare `__fillable__` or `__guarded__` (never both):

```python
class User(ArvelModel):
    __fillable__ = {"name", "email", "bio"}
    # OR
    __guarded__ = {"id", "is_admin", "created_at", "updated_at"}
```

---

## Repository Rules

1. **One repository per model** — no god repositories
2. **Session is private** — callers never see `AsyncSession`
3. **Observer hooks always fire** — `create()`, `update()`, `delete()` dispatch lifecycle events
4. **Custom queries return typed results** — `find_by_email` returns `User | None`, not `Any`
5. **Use `self.query()`** for custom filters — don't build `select()` inside the repository

Keep repositories thin. Complex one-off queries belong in the query builder:

```python
# Compose at the call site
users = await (
    User.query(session)
    .where(User.is_active == True, User.tier == "premium")
    .has("posts", ">", 0)
    .order_by(User.created_at.desc())
    .limit(50)
    .all()
)
```

---

## Query Builder Rules

1. **Use `where(*criteria: ColumnElement[bool])`** — type-safe, parameterized, no injection
2. **Eager-load explicitly** — `with_("posts", "posts.comments")`, never rely on lazy loading
3. **Always `limit()` production queries** — unbounded `all()` is a time bomb
4. **Use `has()` / `where_has()` / `doesnt_have()`** for relationship filtering — not manual joins

### SQL Injection Prevention

All query parameters go through SA's expression engine. String interpolation is forbidden:

```python
# FORBIDDEN
query.where(text(f"name = '{name}'"))

# REQUIRED
query.where(User.name == name)
```

---

## Relationship Rules

1. **Use class references, not strings** — `has_many(Post)` is type-safe
2. **Always specify `back_populates`** for bidirectional relationships
3. **Eager-load at the query level**, not the relationship level

### FK Convention

| Relationship | FK Location | Convention |
|-------------|-------------|-----------|
| `has_one(Profile)` | Profile's table | `{owner_singular}_id` |
| `has_many(Post)` | Post's table | `{owner_singular}_id` |
| `belongs_to(User)` | This model's table | `{related_singular}_id` |
| `belongs_to_many(Role)` | Pivot table | `{singular_a}_{singular_b}` alphabetical |

---

## Transaction Rules

1. **One transaction per business operation** — don't span unrelated work
2. **Keep transactions short** — long transactions hold locks
3. **Use `nested()` savepoints** for partial rollback
4. **Never swallow observer results** — if `dispatch()` returns `False`, abort

---

## Async Session Rules

1. **Request-scoped sessions** — create per request, close on response
2. **`expire_on_commit=False`** — prevents lazy-load errors after commit
3. **`pool_pre_ping=True`** — catches stale connections
4. **Never lazy load in async** — always `selectinload` or `joinedload`

### Connection Pool Defaults

| Setting | Default | Guidance |
|---------|---------|---------|
| `pool_size` | 10 | `2 × CPU cores` |
| `max_overflow` | 5 | `pool_size / 2` |
| `pool_timeout` | 30 | Lower for high-throughput |
| `pool_recycle` | 3600 | Prevent stale connections |
| `pool_pre_ping` | True | Detect disconnects |

---

## Pagination

1. **Cursor-based** for datasets > ~1,000 records
2. **Cap `per_page`** at 100
3. **Order by a unique, stable column** (PK)
4. **Encode cursor values** — don't expose raw column values

---

## Observer Rules

1. **Keep observers lightweight** — they run inside the transaction
2. **Heavy work goes to background jobs**
3. **Register by class, not string**
4. **Always check the return** from pre-event hooks

---

## Performance

### N+1 Prevention

Strict mode (`ARVEL_STRICT_RELATIONS=true`) is ON by default — lazy loads raise `LazyLoadError`. Use `selectinload` for one-to-many, `joinedload` for one-to-one.

### Indexing

- Always index FK columns
- Index columns used in `where()` for frequent queries
- Composite indexes for common multi-column filters
- Don't over-index — each index slows writes

### Bulk Operations

For large inserts, use `session.add_all()` or bulk inserts. Bulk ops bypass observers — dispatch a single batch event instead.

---

## Migrations

1. **One migration per schema change**
2. **Always write `downgrade()`**
3. **Never modify applied migrations**
4. **Data goes in seeders**, not migrations
5. **Two-phase for NOT NULL additions**: add nullable → backfill → make NOT NULL
6. **Review `--autogenerate` output** — it misses index/type changes

---

## Anti-Patterns

| Anti-Pattern | Fix |
|-------------|-----|
| Lazy loading in async | Eager-load with `with_()` |
| Session exposed to controllers | Inject the repository |
| Business logic in models | Move to a service class |
| Unbounded `all()` without `limit()` | Always paginate |
| String interpolation in queries | Use SA expressions |
| Fat repository with 50+ methods | Use query builder for one-off queries |
| Ignoring observer abort signals | Check `dispatch()` return |
| `Column()` in ORM models | Use `Mapped[T]` + `mapped_column()` |
| Missing FK indexes | Add migration with `index=True` |
| Long-running transactions | Keep short; offload to background jobs |
