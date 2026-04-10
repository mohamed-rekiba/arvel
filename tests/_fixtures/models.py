"""Single source of truth for all shared test models.

Every test model used by more than one test package lives here.
Import from this module — don't redefine models in conftest files.
"""

from __future__ import annotations

from typing import ClassVar

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship  # noqa: TC002

from arvel.data.accessors import accessor, mutator
from arvel.data.model import ArvelModel

# ──── General-purpose test models ────


class SampleUser(ArvelModel):
    """Lightweight user for tests that need a simple model (audit, activity)."""

    __tablename__ = "sample_users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    password: Mapped[str] = mapped_column(String(255), default="secret")


class SampleUserWithEmail(ArvelModel):
    """User with email field for testing_pkg (factory, database tests)."""

    __tablename__ = "test_users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)


# ──── Data-layer test models ────


class User(ArvelModel):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    age: Mapped[int | None] = mapped_column(default=None)
    active: Mapped[bool] = mapped_column(default=True)

    posts: Mapped[list[Post]] = relationship(back_populates="author", lazy="selectin")


class Post(ArvelModel):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text, default=None)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    author: Mapped[User] = relationship(back_populates="posts", lazy="selectin")


class FillableUser(ArvelModel):
    """User model with explicit __fillable__ for mass-assignment tests."""

    __tablename__ = "fillable_users"
    __fillable__: ClassVar[set[str]] = {"name", "email", "bio"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    bio: Mapped[str | None] = mapped_column(Text, default=None)
    is_admin: Mapped[bool] = mapped_column(default=False)


class GuardedUser(ArvelModel):
    """User model with explicit __guarded__ for mass-assignment tests."""

    __tablename__ = "guarded_users"
    __guarded__: ClassVar[set[str]] = {"id", "is_admin", "created_at", "updated_at"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    bio: Mapped[str | None] = mapped_column(Text, default=None)
    is_admin: Mapped[bool] = mapped_column(default=False)


# ──── Casting test models ────


class CastUser(ArvelModel):
    """Model with __casts__ for transparent casting tests."""

    __tablename__ = "cast_fixture_users"
    __casts__: ClassVar[dict[str, str]] = {
        "settings": "json",
        "is_verified": "bool",
        "score": "int",
    }

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    settings: Mapped[str | None] = mapped_column(Text, default=None)
    is_verified: Mapped[int | None] = mapped_column(default=None)
    score: Mapped[str | None] = mapped_column(String(50), default=None)


# ──── Mutator test models ────


class MutatorUser(ArvelModel):
    """Model with @mutator for transparent write transforms."""

    __tablename__ = "mutator_users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)

    @mutator("name")
    def set_name(self, value: str) -> str:
        return value.strip().title()


# ──── Serialization test models ────


class HiddenUser(ArvelModel):
    """Model with __hidden__ for serialization tests."""

    __tablename__ = "hidden_users"
    __hidden__: ClassVar[set[str]] = {"password", "secret_token"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password: Mapped[str] = mapped_column(String(255), default="hashed")
    secret_token: Mapped[str | None] = mapped_column(String(255), default=None)


class VisibleUser(ArvelModel):
    """Model with __visible__ (whitelist) for serialization tests."""

    __tablename__ = "visible_users"
    __visible__: ClassVar[set[str]] = {"id", "name", "email"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password: Mapped[str] = mapped_column(String(255), default="hashed")
    internal_notes: Mapped[str | None] = mapped_column(Text, default=None)


class AppendedUser(ArvelModel):
    """Model with __appends__ and an accessor for serialization tests."""

    __tablename__ = "appended_users"
    __appends__: ClassVar[set[str]] = {"display_name"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)

    @accessor("display_name")
    def get_display_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
