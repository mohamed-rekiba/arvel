"""WI-arvel-003 — Framework column DSL parity + RBAC ORM.

Tests are written BEFORE implementation — they FAIL on current code
and PASS after. Covers:
  FR-001: decimal() column helper
  FR-002: jsonb() column helper
  FR-003: enum() column helper
  FR-004: foreign_uuid() column helper
  FR-005: uuid() exported from arvel.database.columns
  FR-006: Role.level in arvel_permission
  FR-007: HasRoles.has_level() in arvel_permission
  FR-008: PublishableMixin in arvel.database.mixins
  FR-009: parse_trashed_mode() in arvel.database.mixins
  FR-010: TranslatableMixin.translate_dict()
  FR-011: cart.py / order.py FK user_id has no default=0
  NFR-003: only_trashed() used in services
  NFR-004: no DB.scalar/DB.table in app/ (non-seeder)
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).parents[5]
ARVEL_COLS = _ROOT / "packages" / "arvel" / "src" / "arvel" / "database" / "columns.py"
ARVEL_MIXINS = _ROOT / "packages" / "arvel" / "src" / "arvel" / "database" / "mixins.py"
ARVEL_PERM_MODELS = (
    _ROOT / "packages" / "arvel-permission" / "src" / "arvel_permission" / "models.py"
)
ARVEL_PERM_TRAITS = (
    _ROOT / "packages" / "arvel-permission" / "src" / "arvel_permission" / "traits.py"
)
DEMO = Path(__file__).parents[2]


def _src(p: Path) -> str:
    return p.read_text()


# ─── FR-001: decimal() ────────────────────────────────────────────────────────


def test_decimal_in_columns_all() -> None:
    """FR-001: decimal exported in __all__."""
    src = _src(ARVEL_COLS)
    assert '"decimal"' in src or "'decimal'" in src, "decimal not in __all__"


def test_decimal_function_signature() -> None:
    """FR-001: decimal(precision, scale) signature."""
    src = _src(ARVEL_COLS)
    assert "def decimal(" in src


def test_decimal_uses_numeric() -> None:
    """FR-001: decimal() uses sqlalchemy Numeric."""
    src = _src(ARVEL_COLS)
    assert "Numeric" in src


def test_decimal_demo_models_use_it() -> None:
    """FR-001: demo numeric money columns use decimal()."""
    for fname in ["cart_item.py", "order_item.py", "order.py"]:
        src = _src(DEMO / "app/models" / fname)
        assert "decimal(" in src, f"FR-001 FAIL: {fname} does not use decimal()"
        assert "Numeric" not in src, f"FR-001 FAIL: {fname} still has raw Numeric"


# ─── FR-002: jsonb() ──────────────────────────────────────────────────────────


def test_jsonb_in_columns_all() -> None:
    """FR-002: jsonb exported in __all__."""
    src = _src(ARVEL_COLS)
    assert '"jsonb"' in src or "'jsonb'" in src, "jsonb not in __all__"


def test_jsonb_function_signature() -> None:
    """FR-002: jsonb() function exists."""
    src = _src(ARVEL_COLS)
    assert "def jsonb(" in src


def test_jsonb_uses_postgresql_jsonb() -> None:
    """FR-002: jsonb() uses dialects.postgresql.JSONB."""
    src = _src(ARVEL_COLS)
    assert "JSONB" in src and "postgresql" in src


def test_jsonb_demo_models_use_it() -> None:
    """FR-002: demo JSONB columns use jsonb()."""
    for fname in ["category.py"]:
        src = _src(DEMO / "app/models" / fname)
        assert "jsonb(" in src, f"FR-002 FAIL: {fname} does not use jsonb()"


# ─── FR-003: enum() ──────────────────────────────────────────────────────────


def test_enum_in_columns_all() -> None:
    """FR-003: enum exported in __all__."""
    src = _src(ARVEL_COLS)
    assert '"enum"' in src or "'enum'" in src, "enum not in __all__"


def test_enum_function_signature() -> None:
    """FR-003: enum() function exists."""
    src = _src(ARVEL_COLS)
    assert "def enum(" in src


def test_enum_demo_models_use_it() -> None:
    """FR-003: demo status/theme columns use enum()."""
    for fname in ["user.py", "order.py", "category.py", "vendor.py"]:
        src = _src(DEMO / "app/models" / fname)
        assert "enum(" in src, f"FR-003 FAIL: {fname} does not use enum()"


# ─── FR-004: foreign_uuid() ───────────────────────────────────────────────────


def test_foreign_uuid_in_columns_all() -> None:
    """FR-004: foreign_uuid exported in __all__."""
    src = _src(ARVEL_COLS)
    assert '"foreign_uuid"' in src or "'foreign_uuid'" in src, "foreign_uuid not in __all__"


def test_foreign_uuid_function_signature() -> None:
    """FR-004: foreign_uuid(references) signature."""
    src = _src(ARVEL_COLS)
    assert "def foreign_uuid(" in src
    assert "references" in src


def test_foreign_uuid_demo_models_use_it() -> None:
    """FR-004: demo UUID FK columns use foreign_uuid()."""
    for fname in ["cart_item.py", "order_item.py"]:
        src = _src(DEMO / "app/models" / fname)
        assert "foreign_uuid(" in src, f"FR-004 FAIL: {fname} does not use foreign_uuid()"


# ─── FR-005: uuid() exported ──────────────────────────────────────────────────


def test_uuid_in_columns_all() -> None:
    """FR-005: uuid exported in __all__."""
    src = _src(ARVEL_COLS)
    assert '"uuid"' in src or "'uuid'" in src, "uuid not in __all__"


# ─── FR-006: Role.level ───────────────────────────────────────────────────────


def test_role_level_field_in_model() -> None:
    """FR-006: arvel_permission.Role has level field."""
    src = _src(ARVEL_PERM_MODELS)
    assert "level" in src, "Role.level not found in arvel_permission/models.py"


def test_role_level_uses_integer_helper() -> None:
    """FR-006: Role.level uses integer() column helper."""
    src = _src(ARVEL_PERM_MODELS)
    assert "integer(" in src and "level" in src


def test_arvel_permission_migration_has_level() -> None:
    """FR-006: arvel_permission create_permission_tables migration includes level."""
    migration = (
        _ROOT
        / "packages"
        / "arvel-permission"
        / "src"
        / "arvel_permission"
        / "migrations"
        / "create_permission_tables.py"
    )
    src = migration.read_text()
    assert "level" in src, "arvel_permission migration missing level column in roles"


# ─── FR-007: HasRoles.has_level() ────────────────────────────────────────────


def test_has_level_in_traits() -> None:
    """FR-007: HasRoles.has_level() method exists in arvel_permission.traits."""
    src = _src(ARVEL_PERM_TRAITS)
    assert "def has_level(" in src


def test_has_level_is_sync() -> None:
    """FR-007: has_level() is synchronous (no async def)."""
    src = _src(ARVEL_PERM_TRAITS)
    assert "async def has_level(" not in src
    assert "def has_level(" in src


def test_user_model_no_raw_has_level() -> None:
    """FR-007: User model no longer defines has_level() via raw SQL."""
    src = _src(DEMO / "app/models/user.py")
    assert "DB.scalar" not in src, "User.has_level still uses DB.scalar raw SQL"
    assert "model_has_roles" not in src, "User.has_level still joins model_has_roles raw"


def test_deps_no_role_level_raw_sql() -> None:
    """FR-007: _deps.py role_level() no longer uses DB.scalar."""
    src = _src(DEMO / "app/http/controllers/_deps.py")
    assert "DB.scalar" not in src, "_deps.py still has raw DB.scalar"


# ─── FR-008: PublishableMixin ─────────────────────────────────────────────────


def test_publishable_mixin_in_mixins() -> None:
    """FR-008: PublishableMixin defined in arvel.database.mixins."""
    src = _src(ARVEL_MIXINS)
    assert "class PublishableMixin" in src


def test_publishable_mixin_has_resolve_published_at() -> None:
    """FR-008: PublishableMixin.resolve_published_at() exists."""
    src = _src(ARVEL_MIXINS)
    assert "def resolve_published_at(" in src


def test_category_service_no_resolved_published_at() -> None:
    """FR-008: category_service.py no longer defines _resolved_published_at."""
    src = _src(DEMO / "app/services/category_service.py")
    assert "_resolved_published_at" not in src, (
        "category_service.py still defines _resolved_published_at()"
    )


def test_vendor_service_no_resolved_published_at() -> None:
    """FR-008: vendor_service.py no longer defines _resolved_published_at."""
    src = _src(DEMO / "app/services/vendor_service.py")
    assert "_resolved_published_at" not in src, (
        "vendor_service.py still defines _resolved_published_at()"
    )


# ─── FR-009: parse_trashed_mode() ────────────────────────────────────────────


def test_parse_trashed_mode_in_mixins() -> None:
    """FR-009: parse_trashed_mode() function in arvel.database.mixins."""
    src = _src(ARVEL_MIXINS)
    assert "def parse_trashed_mode(" in src


def test_category_service_no_trashed_mode_static() -> None:
    """FR-009: CategoryService no longer has trashed_mode() static method."""
    src = _src(DEMO / "app/services/category_service.py")
    assert "def trashed_mode(" not in src, "category_service.py still defines trashed_mode()"


def test_vendor_service_no_trashed_mode_static() -> None:
    """FR-009: VendorService no longer has trashed_mode() static method."""
    src = _src(DEMO / "app/services/vendor_service.py")
    assert "def trashed_mode(" not in src, "vendor_service.py still defines trashed_mode()"


def test_services_use_only_trashed() -> None:
    """NFR-003: services use only_trashed() instead of with_trashed().where_not_null."""
    for fname in ["category_service.py", "vendor_service.py"]:
        src = _src(DEMO / "app/services" / fname)
        assert "only_trashed()" in src, f"NFR-003 FAIL: {fname} doesn't use only_trashed()"
        assert (
            ".where_not_null" not in src
            or "deleted_at" not in src.split(".where_not_null")[0].split("\n")[-1]
        ), f"NFR-003 FAIL: {fname} still uses with_trashed().where_not_null pattern"


# ─── FR-010: TranslatableMixin.translate_dict() ───────────────────────────────


def test_translate_dict_in_mixins() -> None:
    """FR-010: TranslatableMixin.translate_dict() in arvel.database.mixins."""
    src = _src(ARVEL_MIXINS)
    assert "def translate_dict(" in src


def test_product_service_no_translation_private() -> None:
    """FR-010: ProductService._translation() deleted."""
    src = _src(DEMO / "app/services/product_service.py")
    assert "def _translation(" not in src, "ProductService._translation() still exists"


# ─── FR-011: FK user_id no default=0 ─────────────────────────────────────────


def test_cart_user_id_no_default_zero() -> None:
    """FR-011: Cart.user_id has no default=0."""
    src = _src(DEMO / "app/models/cart.py")
    assert "default=0" not in src, "Cart.user_id still has default=0"
    assert "foreign_id(" in src, "Cart.user_id should use foreign_id()"


def test_order_user_id_no_default_zero() -> None:
    """FR-011: Order.user_id has no default=0."""
    src = _src(DEMO / "app/models/order.py")
    assert "default=0" not in src, "Order.user_id still has default=0"
    assert "foreign_id(" in src, "Order.user_id should use foreign_id()"


# ─── NFR-004: no raw DB.scalar/DB.table in app/ ──────────────────────────────


def test_no_raw_db_scalar_in_app() -> None:
    """NFR-004: no DB.scalar or DB.table in app/ (excluding seeder.py)."""
    app_dir = DEMO / "app"
    for py_file in app_dir.rglob("*.py"):
        if "seeder" in py_file.name or "__pycache__" in str(py_file):
            continue
        src = py_file.read_text()
        assert "DB.scalar(" not in src, (
            f"NFR-004 FAIL: raw DB.scalar found in {py_file.relative_to(DEMO)}"
        )
        assert 'DB.table("roles")' not in src, (
            f"NFR-004 FAIL: raw DB.table found in {py_file.relative_to(DEMO)}"
        )
