# Scopes

**Scopes** bundle query constraints you use over and over. **Local scopes** become chainable methods on `QueryBuilder`. **Global scopes** apply automatically until you explicitly opt out — perfect for multi-tenant filters, published-only views, or soft deletes.

Arvel discovers scopes at class creation time and registers them on a per-model `ScopeRegistry`, so everything stays explicit and introspectable.

## Local scopes

Decorate a static or class method with `@scope`. The method receives the current `QueryBuilder` and returns it (possibly chained further).

```python
from arvel.data import ArvelModel
from arvel.data.scopes import scope
from arvel.data.query import QueryBuilder


class User(ArvelModel):
    __tablename__ = "users"

    @scope
    @staticmethod
    def active(query: QueryBuilder["User"]) -> QueryBuilder["User"]:
        return query.where(User.is_active == True)

    @scope
    @staticmethod
    def older_than(query: QueryBuilder["User"], age: int) -> QueryBuilder["User"]:
        return query.where(User.age > age)
```

Call them like fluent methods:

```python
await User.query(session).active().older_than(30).all()
```

Method names may be prefixed with `scope_` — Arvel strips the prefix when registering so `scope_active` becomes `.active()`.

## Global scopes

Subclass `GlobalScope`, implement `apply`, and assign a `name`. Attach instances through `__global_scopes__` on the model:

```python
from arvel.data.scopes import GlobalScope


class PublishedScope(GlobalScope):
    name = "PublishedScope"

    def apply(self, query):
        return query.where(Post.published_at.isnot(None))


class Post(ArvelModel):
    __tablename__ = "posts"
    __global_scopes__ = [PublishedScope()]
```

Every `Post.query()` starts life with those constraints unless you remove them.

## Opting out

When you need the full table — admin tools, reporting, or tests — exclude scopes explicitly:

```python
query.without_global_scope("PublishedScope")
query.without_global_scopes()  # drop every global scope for this builder
```

Soft deletes integrate here: `with_trashed()` and `only_trashed()` manipulate the `SoftDeleteScope` without you remembering column names.

## Composition

Local scopes are plain functions — call other helpers, accept parameters, and return the builder. Global scopes should stay **pure filters**: no I/O, no session side effects — just SQL shape.

Scopes are how a large codebase keeps queries readable. Instead of copying the same `where` clauses into dozens of controllers, you name an idea once and chain it everywhere.
