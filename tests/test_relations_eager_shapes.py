"""Eager loading + where_has/with_count across every relation shape — with
adversarial overlapping ids so a has-many-shaped fallback produces visibly
wrong rows instead of passing by luck."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model


class TagE(Model):
    __fields__ = {"label": str}
    __fillable__ = ["label"]


class PostE(Model):
    __fields__ = {"title": str}
    __fillable__ = ["title"]

    def tags(self) -> object:
        return self.belongs_to_many(
            TagE, pivot="post_tag_e", foreign_pivot_key="poste_id", related_pivot_key="tage_id"
        )


class MemberE(Model):
    __fields__ = {"name": str, "teame_id": int}
    __fillable__ = ["name", "teame_id"]


class GoalE(Model):
    __fields__ = {"points": int, "membere_id": int}
    __fillable__ = ["points", "membere_id"]


class TeamE(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]

    def goals(self) -> object:
        return self.has_many_through(
            GoalE, through=MemberE, first_key="teame_id", second_key="membere_id"
        )

    def first_goal(self) -> object:
        return self.has_one_through(
            GoalE, through=MemberE, first_key="teame_id", second_key="membere_id"
        )


_pivot = sa.Table(
    "post_tag_e",
    sa.MetaData(),
    sa.Column("poste_id", sa.Integer),
    sa.Column("tage_id", sa.Integer),
)


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (TagE, PostE, MemberE, GoalE, TeamE):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    await db.execute(sa.schema.CreateTable(_pivot))
    return db


async def _pivot_fixture(db: ConnectionResolver) -> tuple[object, object]:
    """Two posts, three tags, crossed attachments. Tag ids deliberately overlap
    post ids so shape-confused SQL returns rows that LOOK plausible but are wrong."""
    p1 = await PostE.create(title="p1")  # id 1
    p2 = await PostE.create(title="p2")  # id 2
    t1 = await TagE.create(label="python")  # id 1 — overlaps p1.id
    t2 = await TagE.create(label="async")  # id 2 — overlaps p2.id
    t3 = await TagE.create(label="orm")  # id 3
    await p1.tags().attach(t2.id)
    await p1.tags().attach(t3.id)
    await p2.tags().attach(t1.id)
    return p1, p2


# --- belongs_to_many ----------------------------------------------------------
async def test_belongs_to_many_eager_load_matches_per_parent() -> None:
    db = await _setup()
    try:
        await _pivot_fixture(db)
        posts = await PostE.query().with_("tags").order_by("id").get()
        got = {p.title: sorted(t.label for t in p.relation("tags")) for p in posts}
        assert got == {"p1": ["async", "orm"], "p2": ["python"]}
    finally:
        await db.dispose()


async def test_belongs_to_many_where_has_filters_correctly() -> None:
    db = await _setup()
    try:
        await _pivot_fixture(db)
        titled = [
            p.title
            for p in await PostE.query()
            .where_has("tags", lambda q: q.where("label", "=", "python"))
            .get()
        ]
        assert titled == ["p2"]
    finally:
        await db.dispose()


async def test_belongs_to_many_with_count() -> None:
    db = await _setup()
    try:
        await _pivot_fixture(db)
        posts = await PostE.query().with_count("tags").order_by("id").get()
        assert [p.tags_count for p in posts] == [2, 1]
    finally:
        await db.dispose()


# --- has_many_through / has_one_through ----------------------------------------
async def _through_fixture() -> None:
    """Teams/members/goals with member ids shifted so team ids ≠ member ids —
    a query correlating the wrong key returns nonempty-but-wrong sets."""
    ta = await TeamE.create(name="alpha")  # id 1
    tb = await TeamE.create(name="beta")  # id 2
    # burn member id 1 on team beta so member.id == team.id collisions cross teams
    m1 = await MemberE.create(name="m1", teame_id=tb.id)  # member id 1 ↔ team 2
    m2 = await MemberE.create(name="m2", teame_id=ta.id)  # member id 2 ↔ team 1
    m3 = await MemberE.create(name="m3", teame_id=ta.id)
    await GoalE.create(points=10, membere_id=m2.id)
    await GoalE.create(points=20, membere_id=m3.id)
    await GoalE.create(points=99, membere_id=m1.id)


async def test_has_many_through_eager_load() -> None:
    db = await _setup()
    try:
        await _through_fixture()
        teams = await TeamE.query().with_("goals").order_by("id").get()
        got = {t.name: sorted(g.points for g in t.relation("goals")) for t in teams}
        assert got == {"alpha": [10, 20], "beta": [99]}
    finally:
        await db.dispose()


async def test_has_one_through_eager_load_is_single() -> None:
    db = await _setup()
    try:
        await _through_fixture()
        teams = await TeamE.query().with_("first_goal").order_by("id").get()
        assert teams[0].relation("first_goal").points in (
            10,
            20,
        )  # a goal of team alpha, hydrated single
        assert teams[1].relation("first_goal").points == 99
    finally:
        await db.dispose()


async def test_has_many_through_where_has() -> None:
    db = await _setup()
    try:
        await _through_fixture()
        names = [
            t.name
            for t in await TeamE.query()
            .where_has("goals", lambda q: q.where("points", ">", 50))
            .get()
        ]
        assert names == ["beta"]
    finally:
        await db.dispose()


# --- where_has on belongs_to ----------------------------------------------------
class AuthorE(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]


class BookE(Model):
    __fields__ = {"title": str, "authore_id": int}
    __fillable__ = ["title", "authore_id"]

    def author(self) -> object:
        return self.belongs_to(AuthorE, foreign_key="authore_id")


async def test_where_has_on_belongs_to() -> None:
    db = ConnectionResolver()
    for model in (AuthorE, BookE):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    try:
        ada = await AuthorE.create(name="ada")
        bob = await AuthorE.create(name="bob")
        await BookE.create(title="notes", authore_id=ada.id)
        await BookE.create(title="logic", authore_id=bob.id)
        titles = [
            b.title
            for b in await BookE.query()
            .where_has("author", lambda q: q.where("name", "=", "ada"))
            .get()
        ]
        assert titles == ["notes"]
    finally:
        await db.dispose()


# --- constrained eager load on the new shapes --------------------------------------
async def test_constrained_eager_load_belongs_to_many() -> None:
    db = await _setup()
    try:
        await _pivot_fixture(db)
        posts = (
            await PostE.query()
            .with_(tags=lambda q: q.where("label", "!=", "orm"))
            .order_by("id")
            .get()
        )
        got = {p.title: sorted(t.label for t in p.relation("tags")) for p in posts}
        assert got == {"p1": ["async"], "p2": ["python"]}
    finally:
        await db.dispose()


async def test_constrained_eager_load_has_many_through() -> None:
    db = await _setup()
    try:
        await _through_fixture()
        teams = (
            await TeamE.query()
            .with_(goals=lambda q: q.where("points", ">", 15))
            .order_by("id")
            .get()
        )
        got = {t.name: sorted(g.points for g in t.relation("goals")) for t in teams}
        assert got == {"alpha": [20], "beta": [99]}
    finally:
        await db.dispose()


# --- morph map ---------------------------------------------------------------------
class NoteE(Model):
    __fields__ = {"body": str, "notable_type": str, "notable_id": int}
    __fillable__ = ["body", "notable_type", "notable_id"]


class WidgetE(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]

    def notes(self) -> object:
        return self.morph_many(NoteE, "notable")


async def test_morph_alias_round_trip() -> None:
    from arvel.database import morph_map, morph_type_of

    morph_map({"widget": WidgetE})
    db = ConnectionResolver()
    for model in (NoteE, WidgetE):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    try:
        assert morph_type_of(WidgetE) == "widget"  # every writer routes through this
        w = await WidgetE.create(name="w1")
        await NoteE.create(body="hello", notable_type=morph_type_of(WidgetE), notable_id=w.id)
        notes = await w.notes().get()
        assert [n.body for n in notes] == ["hello"]  # alias-stored rows read back
    finally:
        await db.dispose()


def test_unaliased_morph_type_is_qualified_and_collision_proof() -> None:
    from arvel.database import morph_type_of
    from arvel.database.model import resolve_model

    assert morph_type_of(NoteE) == f"{NoteE.__module__}.NoteE"
    assert resolve_model(f"{NoteE.__module__}.NoteE") is NoteE
    assert resolve_model("NoteE") is None  # bare names no longer resolve (collision-prone)


# --- empty parent set short-circuits ---------------------------------------------
async def test_eager_load_empty_parent_set_runs_no_query() -> None:
    db = await _setup()
    try:
        posts = await PostE.query().where("title", "=", "nope").with_("tags").get()
        assert list(posts) == []
    finally:
        await db.dispose()
