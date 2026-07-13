"""ORM (doc 07) — pivot models: with_pivot / as_ / where_pivot. Test-first."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model


class Rolex(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]


class Userx(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]

    def roles(self) -> object:
        return (
            self.belongs_to_many(
                Rolex, pivot="role_user", foreign_pivot_key="userx_id", related_pivot_key="rolex_id"
            )
            .with_pivot("assigned_at")
            .as_("membership")
        )


_pivot = sa.Table(
    "role_user",
    sa.MetaData(),
    sa.Column("userx_id", sa.Integer),
    sa.Column("rolex_id", sa.Integer),
    sa.Column("assigned_at", sa.String),
)


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (Userx, Rolex):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    await db.execute(sa.schema.CreateTable(_pivot))
    return db


async def test_with_pivot_exposes_pivot_data_via_accessor() -> None:
    db = await _setup()
    try:
        user = await Userx.create(name="ada")
        role = await Rolex.create(name="editor")
        await user.roles().attach(role.id, assigned_at="2026-06-01")

        roles = await user.roles().get()
        assert len(roles) == 1
        assert roles[0].membership["assigned_at"] == "2026-06-01"  # pivot data on the accessor
    finally:
        await db.dispose()


async def test_where_pivot_filters_by_pivot_column() -> None:
    db = await _setup()
    try:
        user = await Userx.create(name="ada")
        early = await Rolex.create(name="early")
        late = await Rolex.create(name="late")
        await user.roles().attach(early.id, assigned_at="2026-01-01")
        await user.roles().attach(late.id, assigned_at="2026-12-31")

        recent = await user.roles().where_pivot("assigned_at", "2026-12-31").get()
        assert {r.name for r in recent} == {"late"}
    finally:
        await db.dispose()


async def test_belongs_to_many_proxy_async_prefetch_runs_once_across_two_terminals() -> None:
    """The DR-0045 once-guard: a proxied builder awaited twice (``get()`` then ``count()``) only
    runs the pivot pre-query once, and both terminals still see the correctly pivot-scoped
    result — not an empty/unscoped one from a dropped or doubled prefetch."""
    db = await _setup()
    try:
        user = await Userx.create(name="ada")
        role = await Rolex.create(name="editor")
        await user.roles().attach(role.id, assigned_at="2026-01-01")

        builder = user.roles().where_in("id", [role.id])
        assert builder._prepared is False

        first = await builder.get()
        assert builder._prepared is True
        assert [m.name for m in first] == ["editor"]

        second = await builder.count()  # same builder, second terminal
        assert second == 1  # still scoped correctly — the prefetch didn't re-run or vanish
    finally:
        await db.dispose()
