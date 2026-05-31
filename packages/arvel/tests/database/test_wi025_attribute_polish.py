"""WI-arvel-025 — Epic 006 Story 14: attribute API polish bundle.

Covers append/set_appends, make_hidden_if/make_visible_if, only/except_, get_key/get_key_name,
qualify_column, is_same/is_not, discard_changes, and the HasUuids/HasUlids traits.
"""

from __future__ import annotations

from typing import ClassVar

from arvel.database import HasUlids, HasUuids, Model
from arvel.database.attributes import accessor
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

_CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


class Wi025Person(Model):
    __tablename__ = "wi025_people"
    __hidden__: ClassVar[list[str] | None] = ["secret"]
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    secret: Mapped[str] = mapped_column(String(80), nullable=False, default="x")

    @accessor
    def display(self) -> str:
        return f"Mr. {self.name}"


class Wi025UuidDoc(Model, HasUuids):
    __tablename__ = "wi025_uuid_docs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(80), nullable=False)


class Wi025UlidDoc(Model, HasUlids):
    __tablename__ = "wi025_ulid_docs"
    id: Mapped[str] = mapped_column(String(26), primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(80), nullable=False)


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class TestAppends:
    def test_append_adds_accessor_to_dict(self) -> None:
        p = Wi025Person(name="Ada")
        assert "display" not in p.to_dict()
        p.append("display")
        assert p.to_dict()["display"] == "Mr. Ada"

    def test_set_appends_replaces_list(self) -> None:
        p = Wi025Person(name="Ada")
        p.append("display")
        p.set_appends([])
        assert "display" not in p.to_dict()


class TestVisibilityConditionals:
    def test_make_hidden_if_true_hides(self) -> None:
        p = Wi025Person(name="Ada")
        p.make_hidden_if(True, "name")
        assert "name" not in p.to_dict()

    def test_make_hidden_if_false_keeps(self) -> None:
        p = Wi025Person(name="Ada")
        p.make_hidden_if(False, "name")
        assert "name" in p.to_dict()

    def test_make_visible_if_callable(self) -> None:
        p = Wi025Person(name="Ada")
        p.make_hidden("name")
        p.make_visible_if(lambda m: m.name == "Ada", "name")
        assert "name" in p.to_dict()


class TestOnlyExcept:
    def test_only(self) -> None:
        p = Wi025Person(name="Ada")
        assert p.only("name") == {"name": "Ada"}

    def test_except(self) -> None:
        p = Wi025Person(name="Ada")
        result = p.except_("secret", "id")
        assert "secret" not in result
        assert result["name"] == "Ada"


class TestKeyHelpers:
    def test_get_key_name(self) -> None:
        assert Wi025Person.get_key_name() == "id"

    async def test_get_key_value(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        p = await Wi025Person.create(name="Ada")
        assert p.get_key() == p.id

    def test_qualify_column(self) -> None:
        assert Wi025Person.qualify_column("email") == "wi025_people.email"


class TestIdentity:
    async def test_is_same_and_is_not(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        a = await Wi025Person.create(name="A")
        b = await Wi025Person.create(name="B")
        same_a = await Wi025Person.find(a.id)
        assert a.is_same(same_a)
        assert a.is_not(b)
        assert a.is_not(None)


class TestDiscardChanges:
    async def test_discard_reverts_dirty(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        p = await Wi025Person.create(name="Ada")
        p.name = "Changed"
        assert p.is_dirty("name")
        p.discard_changes()
        assert p.name == "Ada"
        assert not p.is_dirty("name")


class TestUniqueIdTraits:
    async def test_uuid_generated_on_insert(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        doc = await Wi025UuidDoc.create(title="t")
        assert isinstance(doc.id, str)
        assert len(doc.id) == 36
        assert doc.id.count("-") == 4

    async def test_ulid_generated_on_insert_and_sortable(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        first = await Wi025UlidDoc.create(title="a")
        second = await Wi025UlidDoc.create(title="b")
        assert len(first.id) == 26 and len(second.id) == 26
        # The 10-char time prefix is the sortable part; the random tail isn't
        # monotonic within the same millisecond.
        assert second.id[:10] >= first.id[:10]
        assert set(first.id) <= set(_CROCKFORD_ALPHABET)

    def test_new_unique_id_classmethods(self) -> None:
        assert isinstance(Wi025UuidDoc.new_unique_id(), str)
        assert len(Wi025UlidDoc.new_unique_id()) == 26
