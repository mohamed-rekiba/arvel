# Relationships

Data rarely lives in a single table. Arvel maps associations with declarative helpers — `has_one`, `has_many`, `belongs_to`, `belongs_to_many`, and polymorphic variants — that expand into real SQLAlchemy `relationship()` calls during class construction.

The API encourages **class references** instead of string names: your IDE and `mypy` / `ty` see the related model, and mistakes surface before runtime.

## The big four

Declare the side that owns the foreign key first (here `Post` holds `author_id`), then wire the inverse collection on `User`. Use a string related name where the class is not defined yet; switch to `has_many(Post, …)` once both classes exist if you want the extra type inference.

```python
from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from arvel.data import ArvelModel
from arvel.data.relationships import belongs_to, has_many


class Post(ArvelModel):
    __tablename__ = "posts"

    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    author = belongs_to("User", back_populates="posts")


class User(ArvelModel):
    __tablename__ = "users"

    posts: list[Post] = has_many(Post, back_populates="author")
```

`back_populates` keeps bidirectional navigation honest — define both sides once and Arvel wires the foreign keys and join tables for you.

## Many-to-many

`belongs_to_many` declares the pivot implicitly using naming conventions (alphabetical singular table names when Arvel generates the secondary table). Override the secondary table or foreign keys when your schema does not match the defaults.

## Polymorphic relations

Morph helpers cover the classic "comment can belong to a post or a video" pattern. Arvel exposes `morph_to` (child side), `morph_many` (parent side), and `morph_to_many` for tag-style pivots. Register short type aliases with `register_morph_type` so `{name}_type` / `{name}_id` columns resolve to concrete model classes, and use `load_morph_parent` or `query_morph_children` when you need explicit eager loads — polymorphic paths bypass ordinary `selectinload` because the target table varies by row.

## Eager loading

Async code should not rely on transparent lazy loads. Use `QueryBuilder.with_()` to `selectinload` paths you need:

```python
await User.query(session).with_("posts", "posts.comments").all()
```

Dot syntax nests arbitrarily deep: `posts.comments.author` loads three hops in one shot.

## Strict mode and LazyLoadError

When `ARVEL_STRICT_RELATIONS` is enabled (the common default), touching an unloaded relationship raises `LazyLoadError` instead of quietly issuing another query. That sounds harsh until you realize it catches N+1 bugs in development. Fix it by eager loading or by restructuring the query — never by silencing the error.

## Filtering across relationships

Prefer query-builder helpers over hand-rolled joins when you can:

- `has("posts")` — at least N related rows.
- `doesnt_have("posts")` — no related rows.
- `where_has("posts", lambda Post: …)` — related rows matching extra criteria.

They read like Laravel, compile to efficient SQL, and keep foreign-key resolution centralized.

## Ownership and transactions

Repositories load and save related graphs inside transactions. If you delete a parent, think about observers or database-level `ON DELETE` — Arvel gives you hooks for both.

Relationships are the glue of your domain model. Name them well, eager load deliberately, and let strict mode teach you where the graph was wider than you thought.
