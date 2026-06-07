"""``column_attr`` — ``@declared_attr`` wrapper that auto-injects ``Mapped[T]``.

This module deliberately omits ``from __future__ import annotations`` so the
non-string branch of ``column_attr`` (evaluated type annotations) exercises.
"""

from arvel.database.orm._column_attr import column_attr
from sqlalchemy.orm import Mapped, declared_attr


def test_wraps_plain_string_annotation_in_mapped() -> None:
    def col(_self: object) -> int:
        return 0

    # Override the annotation post-hoc to simulate `from __future__ import annotations`
    # in the defining module — column_attr is supposed to handle both shapes.
    col.__annotations__["return"] = "uuid.UUID"

    wrapped = column_attr(col)

    assert isinstance(wrapped, declared_attr)
    assert col.__annotations__["return"] == "Mapped[uuid.UUID]"


def test_leaves_already_mapped_string_annotation_alone() -> None:
    def col(_self: object) -> int:
        return 0

    col.__annotations__["return"] = "Mapped[uuid.UUID]"

    column_attr(col)

    assert col.__annotations__["return"] == "Mapped[uuid.UUID]"


def test_wraps_evaluated_non_mapped_type_in_mapped() -> None:
    def col(_self: object) -> int:
        return 0

    column_attr(col)

    ret = col.__annotations__["return"]
    assert getattr(ret, "__origin__", None) is Mapped


def test_leaves_evaluated_mapped_type_alone() -> None:
    def col(_self: object) -> Mapped[int]:
        raise NotImplementedError

    column_attr(col)

    ret = col.__annotations__["return"]
    assert getattr(ret, "__origin__", None) is Mapped


def test_skips_when_no_return_annotation() -> None:
    def col(_self: object) -> int:
        return 0

    del col.__annotations__["return"]
    wrapped = column_attr(col)

    assert isinstance(wrapped, declared_attr)
    assert "return" not in col.__annotations__
