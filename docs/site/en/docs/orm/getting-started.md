# ORM: Getting Started

**Arvel** v0.1.0+ targets **Python 3.14+** and maps database rows with SQLAlchemy 2.0 style `Mapped[T]` columns — the same mental model as the rest of this documentation.

Arvel’s ORM sits on **SQLAlchemy 2.0** with async sessions throughout. The centerpiece is `ArvelModel`: a declarative base that knows how to relate models, cast attributes, honor mass-assignment guards, and expose a fluent `query()` entry point that returns a typed `QueryBuilder`.

If you are coming from Laravel, think Eloquent’s ergonomics with Python’s type checkers watching your back. If you are coming from raw SQLAlchemy, think less boilerplate and fewer chances to accidentally lazy-load in async code.

## Defining a model

Subclass `ArvelModel`, set `__tablename__` (or let Arvel pluralize the class name), and declare columns with `Mapped[]` and `mapped_column()` — the SA 2.0 style Arvel standardizes on.

```python
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from arvel.data import ArvelModel


class Post(ArvelModel):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text)
```

Timestamps are available on the base: `created_at` and `updated_at` are declared for you with timezone-aware datetimes.

## Conventions that save typing

Table names default to snake_case plurals (`BlogPost` → `blog_posts`). Foreign keys follow `{related_singular}_id`. If English does something irregular (`people`, `addresses`), set `__singular__` on the model so relationship inference stays correct.

## Mass assignment

Protect writes with `__fillable__` or `__guarded__` — same idea as Laravel. The repository and model factories respect these rules so request data cannot silently escalate privileges.

```python
class User(ArvelModel):
    __tablename__ = "users"

    __fillable__ = {"name", "email", "bio"}
```

## Querying from the model

`Model.query(session)` is the front door. Omit the session in fully wired apps where `DatabaseServiceProvider` registered a session factory; pass one explicitly in tests.

```python
post = await Post.query(session).where(Post.id == 1).first()
```

Shortcuts like `Post.find(1, session=session)`, `Post.all(session=session)`, and `Post.count(session=session)` cover common cases without extra noise.

## Creating and updating

Use repositories inside a `Transaction` for business operations — they dispatch observers, enforce fillable/guarded rules, and keep the session private. For quick scripts you can still work through the model helpers, but the transaction boundary is where Arvel expects real application logic to live.

## Validation and serialization

`ArvelModel` builds a Pydantic model from your mapped columns, which powers `model_validate` / `model_dump` compatibility. Pair that with form requests or API layers and you get one schema that serves both persistence and HTTP.

## Next steps

Relationships, collections, casts, observers, and scopes each get their own chapter. Master `Mapped` columns and `query()` first — everything else layers on top without breaking the mental model.
