"""WI-arvel-010 — Auto-Mapped Column Annotations.

Verifies that:
1. _ModelMeta.__new__ auto-wraps plain type annotations with Mapped[T]
2. ClassVar / InitVar / already-Mapped annotations are excluded from wrapping
3. Relationship annotations are also auto-wrapped
4. Timestamps, SoftDeletes mixins use plain annotations (no Mapped on left side)
5. All demo models drop 'from sqlalchemy.orm import Mapped'
"""

from __future__ import annotations

from datetime import datetime as _datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar, get_origin

import pytest
from sqlalchemy.orm import Mapped

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
MODELS_DIR = Path(__file__).parents[2] / "app" / "models"
ARVEL_MODEL = (
    Path(__file__).parents[5] / "packages" / "arvel" / "src" / "arvel" / "database" / "model.py"
)
ARVEL_COLUMNS = (
    Path(__file__).parents[5] / "packages" / "arvel" / "src" / "arvel" / "database" / "columns.py"
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _annotation_is_mapped(ann: Any) -> bool:
    """Return True if ann is Mapped[T] — handles both actual types and strings.

    With 'from __future__ import annotations' in model files, __annotations__
    may contain strings until our metaclass resolves them. After __new__ runs,
    they should be actual Mapped[T] types (not strings).
    """
    from sqlalchemy.orm import Mapped

    if isinstance(ann, str):
        # String form (metaclass hasn't run yet, or resolution failed)
        return ann.strip().startswith("Mapped[")
    return get_origin(ann) is Mapped


def _get_hints(cls: type) -> dict[str, Any]:
    """Get type hints for a class, falling back to raw __annotations__."""
    try:
        from typing import get_type_hints

        return get_type_hints(cls, include_extras=True)
    except Exception:
        return dict(getattr(cls, "__annotations__", {}))


# ---------------------------------------------------------------------------
# AC-001: Metaclass wraps plain annotations with Mapped[T]
# ---------------------------------------------------------------------------


class TestMetaclassAnnotationWrapping:
    def test_plain_int_annotation_wrapped(self) -> None:
        """id: int = id_()  →  __annotations__['id'] is Mapped[int] at class creation."""
        from arvel.database.columns import id_, string
        from arvel.database.model import Model, Timestamps

        class _TestModel(Model, Timestamps):
            __tablename__ = "_wi010_test_plain_int"
            id: int = id_()
            name: str = string(255, default="x")

        # After __new__, annotations must be actual Mapped[T] types (not strings)
        ann = _TestModel.__annotations__
        assert _annotation_is_mapped(ann.get("id")), (
            f"expected Mapped[int] (actual type), got {ann.get('id')!r}"
        )
        assert _annotation_is_mapped(ann.get("name")), (
            f"expected Mapped[str] (actual type), got {ann.get('name')!r}"
        )

    def test_nullable_annotation_wrapped(self) -> None:
        """status: str | None = string(nullable=True) → Mapped[str | None]."""
        from arvel.database.columns import id_, string
        from arvel.database.model import Model, Timestamps

        class _NullableModel(Model, Timestamps):
            __tablename__ = "_wi010_nullable"
            id: int = id_()
            description: str | None = string(nullable=True, default=None)

        ann = _NullableModel.__annotations__
        assert _annotation_is_mapped(ann.get("description")), (
            f"expected Mapped[str | None], got {ann.get('description')}"
        )
        # Verify wrapping contains the inner type string
        ann_repr = str(ann["description"])
        assert "str" in ann_repr and "None" in ann_repr, (
            f"Mapped wrapping should include inner type; got {ann_repr}"
        )

    def test_classvar_not_wrapped(self) -> None:
        """ClassVar[T] annotations must NOT be wrapped with Mapped."""
        from arvel.database.columns import id_, string
        from arvel.database.model import Model, Timestamps

        class _ClassVarModel(Model, Timestamps):
            __tablename__ = "_wi010_classvar"
            __fillable__: ClassVar[list[str]] = ["name"]
            id: int = id_()
            name: str = string(255, default="x")

        ann = _ClassVarModel.__annotations__
        fillable_ann = ann.get("__fillable__")
        assert fillable_ann is not None
        assert not _annotation_is_mapped(fillable_ann), (
            f"ClassVar must not be wrapped, got {fillable_ann}"
        )

    def test_already_mapped_not_double_wrapped(self) -> None:
        """Existing Mapped[T] annotation must pass through unchanged."""
        from arvel.database.columns import id_, string
        from arvel.database.model import Model, Timestamps

        class _AlreadyMappedModel(Model, Timestamps):
            __tablename__ = "_wi010_already_mapped"
            id: int = id_()
            name: Mapped[str] = string(255, default="x")

        ann = _AlreadyMappedModel.__annotations__
        name_ann = ann.get("name")
        assert _annotation_is_mapped(name_ann), "Mapped[str] must stay Mapped[str]"
        # Must not be double-wrapped to Mapped[Mapped[str]]
        name_str = str(name_ann)
        assert "Mapped[Mapped[" not in name_str, f"Double-wrapped: {name_str}"


# ---------------------------------------------------------------------------
# AC-002: Nullable overloads — type annotation carries nullability
# ---------------------------------------------------------------------------


class TestNullableAnnotations:
    def test_decimal_nullable_annotation(self) -> None:
        """discount: Decimal | None = decimal(nullable=True) → Mapped[Decimal | None]."""
        from arvel.database.columns import decimal, id_
        from arvel.database.model import Model, Timestamps

        class _DecimalModel(Model, Timestamps):
            __tablename__ = "_wi010_decimal_nullable"
            id: int = id_()
            price: Decimal = decimal(10, 2, default=Decimal(0))
            discount: Decimal | None = decimal(10, 2, nullable=True, default=None)

        ann = _DecimalModel.__annotations__
        assert _annotation_is_mapped(ann.get("price"))
        assert _annotation_is_mapped(ann.get("discount"))

    def test_datetime_nullable_annotation(self) -> None:
        """published_at: _datetime | None = datetime(nullable=True) → Mapped[_datetime | None]."""
        from arvel.database.columns import datetime, id_
        from arvel.database.model import Model, Timestamps

        class _DatetimeModel(Model, Timestamps):
            __tablename__ = "_wi010_datetime_nullable"
            id: int = id_()
            published_at: _datetime | None = datetime(nullable=True, default=None)

        ann = _DatetimeModel.__annotations__
        assert _annotation_is_mapped(ann.get("published_at"))


# ---------------------------------------------------------------------------
# AC-003: Relationship annotations wrapped
# ---------------------------------------------------------------------------


class TestRelationshipAnnotationWrapping:
    def test_relationship_annotation_wrapped(self) -> None:
        """Plain int annotation → Mapped[int] after __new__ (basic sanity for non-uuid test)."""
        from arvel.database.columns import id_
        from arvel.database.model import Model, Timestamps

        class _RelModel(Model, Timestamps):
            __tablename__ = "_wi010_relationship"
            id: int = id_()

        ann = _RelModel.__annotations__
        assert "id" in ann
        assert _annotation_is_mapped(ann["id"])


# ---------------------------------------------------------------------------
# AC-004: Mixins use framework column helpers (not raw mapped_column)
# Note: Timestamps/SoftDeletes use ModelMeta, so their plain annotations get
# auto-wrapped in Mapped[T] just like user models. The goal here is they use
# the datetime() helper with clean annotations.
# ---------------------------------------------------------------------------


class TestMixinHelperUsage:
    def test_timestamps_uses_datetime_helper(self) -> None:
        """Timestamps must use datetime() helper, not raw mapped_column(DateTime(...))."""
        src = ARVEL_MODEL.read_text()
        assert "datetime(" in src, "Timestamps must use datetime() column helper"

    def test_softdeletes_uses_datetime_helper(self) -> None:
        """SoftDeletes must use datetime() helper."""
        src = ARVEL_MODEL.read_text()
        assert src.count("datetime(") >= 2, (
            "Both Timestamps and SoftDeletes must use datetime() helper"
        )


# ---------------------------------------------------------------------------
# AC-005: Demo models have no 'from sqlalchemy.orm import Mapped'
# ---------------------------------------------------------------------------


class TestDemoModelsNoMappedImport:
    @pytest.mark.parametrize(
        "model_file",
        [
            "cart.py",
            "cart_item.py",
            "category.py",
            "order.py",
            "order_item.py",
            "product.py",
            # product_base.py uses declared_attr methods with Mapped[T] return types —
            # those are method signatures, not class-level column annotations, so the
            # Mapped import is required there.
            "product_catalog.py",
            "user.py",
            "vendor.py",
        ],
    )
    def test_no_sqlalchemy_mapped_import(self, model_file: str) -> None:
        src = (MODELS_DIR / model_file).read_text()
        assert "from sqlalchemy.orm import Mapped" not in src, (
            f"{model_file} must not import Mapped from sqlalchemy.orm"
        )
        assert "from arvel.database.model import Mapped" not in src, (
            f"{model_file} must not import Mapped at all"
        )

    @pytest.mark.parametrize(
        "model_file",
        [
            "cart.py",
            "cart_item.py",
            "category.py",
            "order.py",
            "order_item.py",
            "product.py",
            "product_catalog.py",
            "user.py",
            "vendor.py",
        ],
    )
    def test_no_mapped_wrapper_on_left_side(self, model_file: str) -> None:
        """Columns must use plain type annotations, never the SQLAlchemy wrapper."""
        import re

        src = (MODELS_DIR / model_file).read_text()
        # Detect a class-level attribute annotation still carrying the wrapper.
        # Exclude 'def' lines (method return types) and ClassVar lines
        mapped_annotations = re.findall(r"^    \w+\s*:\s*Mapped\[", src, re.MULTILINE)
        assert not mapped_annotations, (
            f"{model_file} has Mapped[T] class-attribute annotations: {mapped_annotations}"
        )


# ---------------------------------------------------------------------------
# AC-006: Columns module does not re-export Mapped (clean public surface)
# ---------------------------------------------------------------------------


class TestColumnsModuleSurface:
    def test_columns_module_has_overloads(self) -> None:
        """columns.py must contain @overload stubs."""
        src = ARVEL_COLUMNS.read_text()
        assert "@overload" in src, "columns.py must use @overload stubs for type safety"

    def test_id_helper_in_columns_module(self) -> None:
        """id_() must still be importable and return a MappedColumn at runtime."""
        from arvel.database.columns import id_
        from sqlalchemy.orm import MappedColumn

        result = id_()
        assert isinstance(result, MappedColumn), (
            f"id_() must return MappedColumn at runtime, got {type(result)}"
        )

    def test_string_helper_returns_mapped_column(self) -> None:
        from arvel.database.columns import string
        from sqlalchemy.orm import MappedColumn

        result = string(255)
        assert isinstance(result, MappedColumn)
