"""ORM — query scopes: local scope_* methods + global scopes. Test-first."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model, scope


class Article(Model):
    __fields__ = {"title": str, "published": bool}
    __fillable__ = ["title", "published"]

    def scope_published(self, query: Any) -> None:
        query.where(published=True)

    def scope_titled(self, query: Any, title: str) -> None:
        query.where(title=title)


class Tagged(Model):
    """Scopes declared with the ``@scope`` decorator — method named freely (no ``scope_`` prefix)."""

    __fields__ = {"title": str, "published": bool}
    __fillable__ = ["title", "published"]

    @scope
    def live(self, query: Any) -> None:
        query.where(published=True)

    @scope
    def named(self, query: Any, title: str) -> None:
        query.where(title=title)


class Account(Model):
    __fields__ = {"name": str, "active": bool}
    __fillable__ = ["name", "active"]


async def _table(model: type[Model], db: ConnectionResolver) -> None:
    model.set_connection(db)
    await db.execute(sa.schema.CreateTable(model.__table__))


async def test_local_scope_callable_as_query_method() -> None:
    db = ConnectionResolver()
    await _table(Article, db)
    try:
        await Article.create(title="Live", published=True)
        await Article.create(title="Draft", published=False)
        assert {a.title for a in await Article.published().get()} == {"Live"}
    finally:
        await db.dispose()


async def test_local_scope_with_args_and_chaining() -> None:
    db = ConnectionResolver()
    await _table(Article, db)
    try:
        await Article.create(title="Live", published=True)
        await Article.create(title="Other", published=True)
        rows = await Article.published().titled("Live").get()
        assert {a.title for a in rows} == {"Live"}
    finally:
        await db.dispose()


async def test_scope_decorator_callable_as_query_method() -> None:
    db = ConnectionResolver()
    await _table(Tagged, db)
    try:
        await Tagged.create(title="Live", published=True)
        await Tagged.create(title="Draft", published=False)
        assert {a.title for a in await Tagged.live().get()} == {"Live"}
    finally:
        await db.dispose()


async def test_scope_decorator_with_args_and_chaining() -> None:
    db = ConnectionResolver()
    await _table(Tagged, db)
    try:
        await Tagged.create(title="Live", published=True)
        await Tagged.create(title="Other", published=True)
        rows = await Tagged.live().named("Live").get()
        assert {a.title for a in rows} == {"Live"}
    finally:
        await db.dispose()


async def test_global_scope_auto_applied_and_bypassable() -> None:
    db = ConnectionResolver()
    await _table(Account, db)
    Account.add_global_scope("active", lambda q: q.where(active=True))
    try:
        await Account.create(name="On", active=True)
        await Account.create(name="Off", active=False)

        assert {a.name for a in await Account.get()} == {"On"}  # scope applied by default
        everyone = await Account.without_global_scope("active").get()
        assert {a.name for a in everyone} == {"On", "Off"}  # bypassed
    finally:
        Account.__global_scopes__ = {}  # don't leak into other tests
        await db.dispose()
