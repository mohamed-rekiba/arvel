"""Coverage-closing behavioral tests for the less-common `arvel.database.relations` edges:
empty-key short-circuits, pivot/related-constraint branch combinations on BelongsToMany,
has_many_through with a nullable custom local key, morph_to type-collision/unresolved-type
skips, and the belongs_to/has_one/has_many callback-less exists/aggregate paths. Each test
asserts an observable outcome (a returned row set, a raised error, a resolved type) that
would fail if the underlying branch broke — not just "it ran"."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model, morph_map
from arvel.database.relations import BelongsToMany, HasManyThrough, _pk_type


# --- _pk_type: fallback to Integer when the column can't be resolved --------------
class PlainModelForPkType(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]


def test_pk_type_falls_back_to_integer_for_unknown_column() -> None:
    assert isinstance(_pk_type(PlainModelForPkType, "does_not_exist"), sa.Integer)


def test_pk_type_falls_back_to_integer_when_table_attribute_missing() -> None:
    class NotAModel:
        pass

    assert isinstance(_pk_type(NotAModel, "id"), sa.Integer)


# --- base Relation: empty-keys short-circuit + no-op callback branch --------------
class MemberG(Model):
    __fields__ = {"name": str, "groupg_code": str}
    __fillable__ = ["name", "groupg_code"]


class GroupG(Model):
    __fields__ = {"code": str}
    __fillable__ = ["code"]

    def members(self) -> object:
        return self.has_many(MemberG, foreign_key="groupg_code", local_key="code")


async def _setup_group() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (GroupG, MemberG):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


async def test_eager_load_with_null_local_key_short_circuits_to_empty() -> None:
    db = await _setup_group()
    try:
        await GroupG.create(code=None)
        groups = await GroupG.query().with_("members").get()
        assert list(groups[0].relation("members")) == []  # keys=[] path, no query issued
    finally:
        await db.dispose()


async def test_where_has_with_noop_callback_still_filters_has_any() -> None:
    db = await _setup_group()
    try:
        g1 = await GroupG.create(code="a")
        await GroupG.create(code="b")
        await MemberG.create(name="m1", groupg_code=g1.code)

        names = [g.code for g in await GroupG.query().where_has("members", lambda _q: None).get()]
        assert names == ["a"]  # extra=None branch still resolves to a plain EXISTS
    finally:
        await db.dispose()


def test_has_one_or_many_getattr_raises_for_missing_private_attr() -> None:
    group = GroupG(code="x")
    relation = group.members()
    with pytest.raises(AttributeError):
        relation._totally_not_a_real_attribute


async def test_has_one_or_many_proxies_unknown_attrs_to_the_query() -> None:
    db = await _setup_group()
    try:
        group = await GroupG.create(code="g1")
        await MemberG.create(name="zed", groupg_code="g1")
        await MemberG.create(name="ann", groupg_code="g1")
        # order_by isn't defined on the relation itself — proxied via __getattr__ to query()
        names = [m.name for m in await group.members().order_by("name").get()]
        assert names == ["ann", "zed"]
    finally:
        await db.dispose()


async def test_has_many_create_and_save_set_the_foreign_key() -> None:
    db = await _setup_group()
    try:
        group = await GroupG.create(code="g1")
        created = await group.members().create(name="via-create")
        assert created.groupg_code == "g1"

        existing = MemberG(name="via-save")
        saved = await group.members().save(existing)
        assert saved.groupg_code == "g1"

        names = {m.name for m in await group.members().get()}
        assert names == {"via-create", "via-save"}
    finally:
        await db.dispose()


# --- HasOne: empty match on eager load ---------------------------------------------
class ProfileP(Model):
    __fields__ = {"bio": str, "user_p_id": int}
    __fillable__ = ["bio", "user_p_id"]


class UserP(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]

    def profile(self) -> object:
        return self.has_one(ProfileP)


async def test_has_one_eager_load_with_no_match_is_none() -> None:
    db = ConnectionResolver()
    for model in (UserP, ProfileP):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    try:
        await UserP.create(name="lonely")
        users = await UserP.query().with_("profile").get()
        assert users[0].relation("profile") is None
    finally:
        await db.dispose()


# --- BelongsToMany: pivot-where + related-constraint branch combinations ----------
class ItemZ(Model):
    __fields__ = {"name": str, "visible": int}
    __fillable__ = ["name", "visible"]


class ShopZ(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]

    def featured_items(self) -> object:
        # D7: `.where()` is now the full-builder proxy, not a relation-level accumulator — a
        # pivot-specific fluent method (`with_pivot`) can no longer be chained *after* it (that
        # ordering note lives in the E12 architecture doc). Any related-model filter (e.g.
        # "visible") is expressed at the call site now (`.where(...)`, or a `with_()` constrain
        # callback for eager loading) rather than baked into the relation definition.
        return (
            self.belongs_to_many(
                ItemZ,
                pivot="shopz_itemz",
                foreign_pivot_key="shopz_id",
                related_pivot_key="itemz_id",
            )
            .where_pivot("active", 1)
            .with_pivot("added_by")
        )


class BinZ(Model):
    __fields__ = {"slot": str}
    __fillable__ = ["slot"]

    def widgets(self) -> object:
        return BelongsToMany(self, WidgetZ, "binz_widgetz", "slot", "widgetz_id", parent_key="slot")


class WidgetZ(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]


_shopz_itemz = sa.Table(
    "shopz_itemz",
    sa.MetaData(),
    sa.Column("shopz_id", sa.Integer),
    sa.Column("itemz_id", sa.Integer),
    sa.Column("active", sa.Integer),
    sa.Column("added_by", sa.String),
)

_binz_widgetz = sa.Table(
    "binz_widgetz",
    sa.MetaData(),
    sa.Column("slot", sa.String),
    sa.Column("widgetz_id", sa.Integer),
)


async def _setup_shop() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (ShopZ, ItemZ, BinZ, WidgetZ):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    await db.execute(sa.schema.CreateTable(_shopz_itemz))
    await db.execute(sa.schema.CreateTable(_binz_widgetz))
    return db


async def test_belongs_to_many_eager_load_honors_pivot_where_and_related_where() -> None:
    db = await _setup_shop()
    try:
        shop = await ShopZ.create(name="s1")
        keep = await ItemZ.create(name="keep", visible=1)
        hidden = await ItemZ.create(name="hidden", visible=0)
        stale = await ItemZ.create(name="stale", visible=1)
        await shop.featured_items().attach(keep.id, active=1, added_by="ada")
        await shop.featured_items().attach(hidden.id, active=1, added_by="ada")
        await shop.featured_items().attach(stale.id, active=0, added_by="bob")

        # D7: the related-model filter no longer bakes into the relation definition — narrow the
        # eager load with a constrain callback instead (same combined pivot + related filtering,
        # expressed at the call site rather than on featured_items() itself).
        shops = await ShopZ.query().with_(featured_items=lambda q: q.where("visible", "=", 1)).get()
        names = sorted(i.name for i in shops[0].relation("featured_items"))
        assert names == ["keep"]  # only active pivot + visible related row survives both filters
        by_name = {i.name: i for i in shops[0].relation("featured_items")}
        assert by_name["keep"].pivot["added_by"] == "ada"
    finally:
        await db.dispose()


async def test_belongs_to_many_eager_load_with_no_attachments_is_empty() -> None:
    db = await _setup_shop()
    try:
        await ShopZ.create(name="empty-shop")
        shops = await ShopZ.query().with_("featured_items").get()
        assert list(shops[0].relation("featured_items")) == []  # all_related_ids=[] path
    finally:
        await db.dispose()


async def test_belongs_to_many_eager_load_short_circuits_on_null_parent_key() -> None:
    db = await _setup_shop()
    try:
        await BinZ.create(slot=None)
        bins = await BinZ.query().with_("widgets").get()
        assert list(bins[0].relation("widgets")) == []  # parent_ids=[] path
    finally:
        await db.dispose()


async def test_belongs_to_many_has_and_with_count_use_pivot_constraints() -> None:
    db = await _setup_shop()
    try:
        shop = await ShopZ.create(name="s1")
        empty_shop = await ShopZ.create(name="s2")
        keep = await ItemZ.create(name="keep", visible=1)
        hidden = await ItemZ.create(name="hidden", visible=0)
        await shop.featured_items().attach(keep.id, active=1)
        await shop.featured_items().attach(hidden.id, active=1)

        with_any = [s.name for s in await ShopZ.query().has("featured_items").order_by("id").get()]
        assert with_any == ["s1"]  # exists_clause(callback=None) honors the pivot where

        # D7: `has()`/`with_count()` take no callback, and the relation no longer bakes in a
        # related-model where() (that's the proxy's job now) — so both attachments count,
        # regardless of `visible` (2, not the pre-D7 visible-only 1).
        counted = await ShopZ.query().with_count("featured_items").order_by("id").get()
        assert [s.featured_items_count for s in counted] == [2, 0]
        assert empty_shop.name == "s2"
    finally:
        await db.dispose()


async def test_belongs_to_many_order_by_count_and_detach_all() -> None:
    db = await _setup_shop()
    try:
        shop = await ShopZ.create(name="s1")
        a = await ItemZ.create(name="banana", visible=1)
        b = await ItemZ.create(name="apple", visible=1)
        await shop.featured_items().attach(a.id, active=1)
        await shop.featured_items().attach(b.id, active=1)

        ordered = [i.name for i in await shop.featured_items().order_by("name").get()]
        assert ordered == ["apple", "banana"]  # order_by proxies to the pivot-scoped Builder (D7)

        assert await shop.featured_items().count() == 2  # count() honors the pivot where

        await shop.featured_items().detach()  # no related_id: detach every attachment
        assert list(await shop.featured_items().get()) == []
    finally:
        await db.dispose()


async def test_belongs_to_many_sync_reads_only_matching_pivot_wheres() -> None:
    db = await _setup_shop()
    try:
        shop = await ShopZ.create(name="s1")
        keep = await ItemZ.create(name="keep", visible=1)
        await shop.featured_items().attach(keep.id, active=1)

        # sync's _attached_rows filters by the relation's own where_pivot("active", 1)
        result = await shop.featured_items().sync([keep.id])
        assert result.attached == [] and result.detached == []  # already attached+active, retained
    finally:
        await db.dispose()


class PlainTagB(Model):
    __fields__ = {"label": str}
    __fillable__ = ["label"]


class PlainPostB(Model):
    __fields__ = {"title": str}
    __fillable__ = ["title"]

    def tags(self) -> object:
        return self.belongs_to_many(
            PlainTagB,
            pivot="plainpostb_plaintagb",
            foreign_pivot_key="plainpostb_id",
            related_pivot_key="plaintagb_id",
        )


_plainpostb_plaintagb = sa.Table(
    "plainpostb_plaintagb",
    sa.MetaData(),
    sa.Column("plainpostb_id", sa.Integer),
    sa.Column("plaintagb_id", sa.Integer),
)


async def test_belongs_to_many_has_with_no_constraints_at_all() -> None:
    db = ConnectionResolver()
    for model in (PlainPostB, PlainTagB):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    await db.execute(sa.schema.CreateTable(_plainpostb_plaintagb))
    try:
        post = await PlainPostB.create(title="p1")
        await PlainPostB.create(title="p2")
        tag = await PlainTagB.create(label="t1")
        await post.tags().attach(tag.id)

        # no pivot_wheres, no related where(), no callback: extra=None inside exists_clause
        titled = [p.title for p in await PlainPostB.query().has("tags").get()]
        assert titled == ["p1"]
    finally:
        await db.dispose()


# --- HasManyThrough with a nullable custom local key + callback-less clauses -------
class AuthorH(Model):
    __fields__ = {"name": str, "regionh_code": str}
    __fillable__ = ["name", "regionh_code"]


class PostH(Model):
    __fields__ = {"title": str, "authorh_id": int}
    __fillable__ = ["title", "authorh_id"]


class RegionH(Model):
    __fields__ = {"code": str}
    __fillable__ = ["code"]

    def posts(self) -> object:
        return HasManyThrough(
            self,
            PostH,
            AuthorH,
            first_key="regionh_code",
            second_key="authorh_id",
            local_key="code",
            second_local_key="id",
        )


async def _setup_region() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (RegionH, AuthorH, PostH):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


async def test_has_many_through_eager_load_short_circuits_on_null_local_key() -> None:
    db = await _setup_region()
    try:
        await RegionH.create(code=None)
        regions = await RegionH.query().with_("posts").get()
        assert list(regions[0].relation("posts")) == []  # parent_keys=[] path
    finally:
        await db.dispose()


async def test_has_many_through_eager_load_with_no_intermediates_is_empty() -> None:
    db = await _setup_region()
    try:
        r1 = await RegionH.create(code="r1")
        await RegionH.create(code="r2")  # no authors at all in r2
        author = await AuthorH.create(name="a1", regionh_code=r1.code)
        await PostH.create(title="p1", authorh_id=author.id)

        regions = await RegionH.query().with_("posts").order_by("id").get()
        got = {r.code: [p.title for p in r.relation("posts")] for r in regions}
        assert got == {"r1": ["p1"], "r2": []}

        # r2 alone in the batch: intermediates=[] → parent_key_by_link stays empty,
        # skipping the related-model fetch entirely (not just an empty grouped[] result)
        r2_only = await RegionH.query().where("code", "=", "r2").with_("posts").get()
        assert list(r2_only[0].relation("posts")) == []
    finally:
        await db.dispose()


async def test_has_many_through_has_and_where_has_noop_callback() -> None:
    db = await _setup_region()
    try:
        r1 = await RegionH.create(code="r1")
        await RegionH.create(code="r2")
        author = await AuthorH.create(name="a1", regionh_code=r1.code)
        await PostH.create(title="p1", authorh_id=author.id)

        via_has = [r.code for r in await RegionH.query().has("posts").get()]
        assert via_has == ["r1"]  # exists_clause(callback=None)

        via_noop = [r.code for r in await RegionH.query().where_has("posts", lambda _q: None).get()]
        assert via_noop == ["r1"]  # callback given but produces no extra WHERE
    finally:
        await db.dispose()


async def test_has_many_through_with_count_is_a_scalar_subquery() -> None:
    db = await _setup_region()
    try:
        r1 = await RegionH.create(code="r1")
        r2 = await RegionH.create(code="r2")
        author = await AuthorH.create(name="a1", regionh_code=r1.code)
        await PostH.create(title="p1", authorh_id=author.id)
        await PostH.create(title="p2", authorh_id=author.id)

        counted = await RegionH.query().with_count("posts").order_by("id").get()
        assert [r.posts_count for r in counted] == [2, 0]
        assert r2.code == "r2"
    finally:
        await db.dispose()


# --- MorphTo eager load: mixed null target, unresolved type, constrained eager ----
class CommentM(Model):
    __fields__ = {"body": str, "commentablem_type": str, "commentablem_id": int}
    __fillable__ = ["body", "commentablem_type", "commentablem_id"]

    def commentable(self) -> object:
        return self.morph_to("commentablem")


class VideoM(Model):
    __fields__ = {"title": str}
    __fillable__ = ["title"]


morph_map({"VideoM": VideoM})


async def _setup_morph_m() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (CommentM, VideoM):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


async def test_morph_to_eager_load_skips_null_and_unresolved_types() -> None:
    db = await _setup_morph_m()
    try:
        video = await VideoM.create(title="clip")
        await CommentM.create(body="a", commentablem_type="VideoM", commentablem_id=video.id)
        orphan = await CommentM.create(body="b", commentablem_type=None, commentablem_id=None)
        ghost = await CommentM.create(body="c", commentablem_type="Ghost", commentablem_id=1)

        comments = await CommentM.query().with_("commentable").order_by("id").get()
        by_body = {c.body: c.relation("commentable") for c in comments}
        assert by_body["a"] is not None and by_body["a"].title == "clip"
        assert by_body["b"] is None  # null type/id: never grouped (654->651)
        assert by_body["c"] is None  # unresolved type: skipped (661), stays unmatched
        assert orphan.body == "b" and ghost.body == "c"
    finally:
        await db.dispose()


async def test_morph_to_constrained_eager_load_applies_callback() -> None:
    db = await _setup_morph_m()
    try:
        clip = await VideoM.create(title="clip")
        await VideoM.create(title="other")
        await CommentM.create(body="a", commentablem_type="VideoM", commentablem_id=clip.id)

        comments = (
            await CommentM.query().with_(commentable=lambda q: q.where("title", "=", "clip")).get()
        )
        assert comments[0].relation("commentable").title == "clip"
    finally:
        await db.dispose()


# --- MorphOne empty match, MorphToMany/MorphedByMany empty get() -------------------
class ImageA(Model):
    __fields__ = {"url": str, "imageablea_type": str, "imageablea_id": int}
    __fillable__ = ["url", "imageablea_type", "imageablea_id"]


class AccountA(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]

    def image(self) -> object:
        return self.morph_one(ImageA, "imageablea")


async def test_morph_one_eager_load_with_no_match_is_none() -> None:
    db = ConnectionResolver()
    for model in (AccountA, ImageA):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    try:
        await AccountA.create(name="ada")
        accounts = await AccountA.query().with_("image").get()
        assert accounts[0].relation("image") is None
    finally:
        await db.dispose()


class TagH2(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]

    def posts(self) -> object:
        return self.morphed_by_many(PostH2, "taggableh2")


class PostH2(Model):
    __fields__ = {"title": str}
    __fillable__ = ["title"]

    def tags(self) -> object:
        return self.morph_to_many(TagH2, "taggableh2")


_taggables_h2 = sa.Table(
    "taggableh2s",
    sa.MetaData(),
    sa.Column("taggableh2_type", sa.String),
    sa.Column("taggableh2_id", sa.Integer),
    sa.Column("tag_h2_id", sa.Integer),
)


async def test_morph_to_many_and_morphed_by_many_get_empty_when_unattached() -> None:
    db = ConnectionResolver()
    for model in (TagH2, PostH2):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    await db.execute(sa.schema.CreateTable(_taggables_h2))
    try:
        post = await PostH2.create(title="p1")
        tag = await TagH2.create(name="t1")
        assert list(await post.tags().get()) == []  # MorphToMany.get(), no pivot rows
        assert list(await tag.posts().get()) == []  # MorphedByMany.get(), no pivot rows
    finally:
        await db.dispose()


# --- BelongsTo: empty-keys eager load, constrained eager, callback-less clauses ---
class AuthorE2(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]


class BookE2(Model):
    __fields__ = {"title": str, "authore2_id": int}
    __fillable__ = ["title", "authore2_id"]

    def author(self) -> object:
        return self.belongs_to(AuthorE2, foreign_key="authore2_id")


async def _setup_books() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (AuthorE2, BookE2):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


async def test_belongs_to_eager_load_with_null_fk_is_none() -> None:
    db = await _setup_books()
    try:
        await BookE2.create(title="orphan", authore2_id=None)
        books = await BookE2.query().with_("author").get()
        assert books[0].relation("author") is None  # keys=[] short-circuit
    finally:
        await db.dispose()


async def test_belongs_to_constrained_eager_load_applies_callback() -> None:
    db = await _setup_books()
    try:
        ada = await AuthorE2.create(name="ada")
        await BookE2.create(title="notes", authore2_id=ada.id)

        books = await BookE2.query().with_(author=lambda q: q.where("name", "=", "nobody")).get()
        assert books[0].relation("author") is None  # constrained eager load excludes ada
    finally:
        await db.dispose()


async def test_belongs_to_has_and_noop_callback_and_with_count() -> None:
    db = await _setup_books()
    try:
        ada = await AuthorE2.create(name="ada")
        await BookE2.create(title="notes", authore2_id=ada.id)
        await BookE2.create(title="unlinked", authore2_id=None)

        via_has = [b.title for b in await BookE2.query().has("author").get()]
        assert via_has == ["notes"]  # exists_clause(callback=None)

        via_noop = [
            b.title for b in await BookE2.query().where_has("author", lambda _q: None).get()
        ]
        assert via_noop == ["notes"]  # callback given but produces no extra WHERE

        counted = await BookE2.query().with_count("author").order_by("id").get()
        assert [b.author_count for b in counted] == [1, 0]  # aggregate_clause, no callback
    finally:
        await db.dispose()


def test_belongs_to_getattr_raises_for_missing_private_attr() -> None:
    book = BookE2(title="x")
    with pytest.raises(AttributeError):
        book.author()._totally_not_a_real_attribute


async def test_belongs_to_proxies_unknown_attrs_associates_and_dissociates() -> None:
    db = await _setup_books()
    try:
        ada = await AuthorE2.create(name="ada")
        bob = await AuthorE2.create(name="bob")
        book = await BookE2.create(title="notes", authore2_id=ada.id)

        # order_by isn't defined on BelongsTo itself — proxied via __getattr__ to query()
        names = [a.name for a in await book.author().order_by("name").get()]
        assert names == ["ada"]

        book.author().associate(bob)
        assert book.authore2_id == bob.id  # fk set to the new owner's key, not yet persisted

        book.author().dissociate()
        assert book.authore2_id is None
    finally:
        await db.dispose()
