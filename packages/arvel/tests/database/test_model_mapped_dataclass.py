"""Tests for MappedAsDataclass integration on the Model base class (ADR-076)."""

from __future__ import annotations

import contextlib
import dataclasses
import importlib.util
import inspect
import re
from pathlib import Path
from typing import Any

import pytest
from arvel.database import Model, Timestamps, field, id_, relationship, string

# ─── fixtures ────────────────────────────────────────────────────────────────


class Article(Model, Timestamps):
    __tablename__ = "articles_dc_test"

    id: int = id_(init=False)
    title: str = string(200)
    body: str | None = string(5000, nullable=True, default=None)


class Tag(Model):
    __tablename__ = "tags_dc_test"

    id: int = id_(init=False)
    name: str = string(80)
    article_id: int | None = field(foreign_key="articles_dc_test.id", default=None)
    article: Article | None = relationship("Article", init=False)


# ─── FR-076-001: typed keyword-only __init__ ─────────────────────────────────


def test_model_is_dataclass() -> None:
    assert dataclasses.is_dataclass(Article)
    assert dataclasses.is_dataclass(Tag)


def test_constructor_accepts_typed_keyword_args() -> None:
    a = Article(title="Hello", body="World")
    assert a.title == "Hello"
    assert a.body == "World"


def test_constructor_optional_field_has_default() -> None:
    a = Article(title="Hello")
    assert a.body is None


def test_constructor_is_keyword_only() -> None:
    for param in inspect.signature(Article).parameters.values():
        assert param.kind is inspect.Parameter.KEYWORD_ONLY


def test_server_managed_pk_not_in_init() -> None:
    """id_ fields with init=False must not appear in the constructor."""
    fields = {f.name: f for f in dataclasses.fields(Article)}
    assert fields["id"].init is False


def test_timestamps_not_in_init() -> None:
    """Timestamps mixin fields must not appear in the constructor."""
    fields = {f.name: f for f in dataclasses.fields(Article)}
    assert fields["created_at"].init is False
    assert fields["updated_at"].init is False


def test_relationship_not_in_init() -> None:
    """Relationships with init=False must not appear in the constructor."""
    fields = {f.name: f for f in dataclasses.fields(Tag)}
    assert fields["article"].init is False


# ─── FR-076-002: missing required field raises TypeError ─────────────────────


def test_missing_required_field_raises() -> None:
    with pytest.raises(TypeError):
        Article()  # type: ignore[call-arg]  # intentional negative test


# ─── FR-076-003: dataclass_transform metaclass propagates to subclasses ──────


def test_custom_model_class_is_dataclass() -> None:
    """dataclass_transform on Model propagates to arbitrary subclasses."""
    assert dataclasses.is_dataclass(Tag)
    init_field_names = {f.name for f in dataclasses.fields(Tag) if f.init}
    assert init_field_names == {"name", "article_id"}


# ─── FR-076-004: instance_hidden unaffected ──────────────────────────────────


def test_instance_hidden_is_class_var_not_dataclass_field() -> None:
    """_instance_hidden must be ClassVar — not a dataclass field."""
    field_names = {f.name for f in dataclasses.fields(Article)}
    assert "_instance_hidden" not in field_names


# ─── FR-076-005: to_dict / to_schema still work ──────────────────────────────


@pytest.mark.asyncio
async def test_to_dict_includes_mapped_columns(engine: Any, session: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Article.metadata.create_all)

    a = Article(title="Dict test", body="some body")
    session.add(a)
    await session.flush()

    d = a.to_dict()
    assert d["title"] == "Dict test"
    assert d["body"] == "some body"
    assert "id" in d


# ─── ARCH-001: column helpers produce Mapped[T]-annotated attributes ─────────


def test_arvel_model_module_has_no_untyped_mapped_columns() -> None:
    """Every mapped_column() assignment in model.py must be Mapped[T]-annotated.

    Catches regressions where a developer adds a bare `col = mapped_column()`
    without the required `Mapped[T]` annotation that MappedAsDataclass depends on.
    """
    spec = importlib.util.find_spec("arvel.database.model")
    assert spec is not None and spec.origin is not None
    source = Path(spec.origin).read_text()

    # Lines that assign mapped_column() but lack a Mapped[...] annotation.
    bad_lines = [
        line
        for line in source.splitlines()
        if re.search(r"=\s*mapped_column\(", line)
        and "Mapped[" not in line
        # Exclude comment lines and the @overload stubs in the module itself.
        and not line.lstrip().startswith("#")
    ]
    assert bad_lines == [], (
        "model.py has mapped_column() assignments without Mapped[T] annotations:\n"
        + "\n".join(bad_lines)
    )


def test_columns_module_has_no_untyped_mapped_columns() -> None:
    """Every mapped_column() assignment in columns.py must be Mapped[T]-annotated."""
    spec = importlib.util.find_spec("arvel.database.columns")
    assert spec is not None and spec.origin is not None
    source = Path(spec.origin).read_text()

    bad_lines = [
        line
        for line in source.splitlines()
        if re.search(r"=\s*mapped_column\(", line)
        and "Mapped[" not in line
        and not line.lstrip().startswith("#")
    ]
    assert bad_lines == [], (
        "columns.py has mapped_column() assignments without Mapped[T] annotations:\n"
        + "\n".join(bad_lines)
    )


def test_model_base_all_columns_carry_mapped_annotation() -> None:
    """Introspect the Model class: every SQLAlchemy column attribute on the class
    body must be reflected as a Mapped[T] type hint (not bare Column)."""
    import arvel.database.model as mod

    for cls in (mod.Model, mod.Timestamps, mod.SoftDeletes):
        hints: dict[str, object] = {}
        with contextlib.suppress(AttributeError):
            hints = inspect.get_annotations(cls)
        for attr_name, hint in hints.items():
            if attr_name.startswith("_"):
                continue
            hint_str = str(hint)
            if "MappedColumn" in hint_str or "mapped_column" in hint_str.lower():
                assert "Mapped" in hint_str, (
                    f"{cls.__name__}.{attr_name} is mapped_column but missing Mapped[T]"
                )
