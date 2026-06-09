"""Framework cleanup and kit hardening.

All tests must FAIL before implementation and PASS after.

FK defaults removed from CartItem / OrderItem
uuid_id() in arvel.database.columns
TranslatableMixin in arvel.database.mixins
Auth guards in arvel.auth.guards
Kit auth controller uses framework AuthController
CartItem.id and OrderItem.id are integer (BIGSERIAL)
"""

from __future__ import annotations

from pathlib import Path

from _framework_src import ARVEL_SRC

BASE = Path(__file__).parents[2]
ARVEL_DB_COLS = ARVEL_SRC / "database" / "columns.py"
ARVEL_DB_MIXINS = ARVEL_SRC / "database" / "mixins.py"
ARVEL_AUTH_GUARDS = ARVEL_SRC / "auth" / "guards" / "__init__.py"
CART_ITEM_MODEL = BASE / "app" / "models" / "cart_item.py"
ORDER_ITEM_MODEL = BASE / "app" / "models" / "order_item.py"
AUTH_CTRL = BASE / "app" / "http" / "controllers" / "auth.py"
ROUTES_API = BASE / "routes" / "api.py"


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ── FK defaults removed ──────────────────────────────────────────────


def test_cart_item_cart_id_has_no_default_factory() -> None:
    src = _src(CART_ITEM_MODEL)
    # Clean FK helper, never a default_factory PK pattern
    assert "cart_id: uuid.UUID = foreign_uuid(" in src
    assert "default_factory" not in src


def test_cart_item_product_id_has_no_default_factory() -> None:
    src = _src(CART_ITEM_MODEL)
    assert "product_id: uuid.UUID = foreign_uuid(" in src
    assert "default_factory" not in src


def test_order_item_order_id_has_no_default_factory() -> None:
    src = _src(ORDER_ITEM_MODEL)
    assert "order_id: uuid.UUID = foreign_uuid(" in src
    assert "default_factory" not in src


# ── uuid_id() in framework ───────────────────────────────────────────


def test_uuid_id_exists_in_arvel_columns() -> None:
    assert ARVEL_DB_COLS.exists(), "arvel/database/columns.py not found"
    src = _src(ARVEL_DB_COLS)
    assert "def uuid_id(" in src


def test_uuid_id_exported_from_arvel_columns() -> None:
    assert ARVEL_DB_COLS.exists()
    src = _src(ARVEL_DB_COLS)
    assert "uuid_id" in src
    assert "__all__" in src
    assert '"uuid_id"' in src or "'uuid_id'" in src


def test_kit_models_use_uuid_id() -> None:
    """All UUID-PK models in the kit use uuid_id() not raw mapped_column."""
    model_files = [
        BASE / "app" / "models" / "vendor.py",
        BASE / "app" / "models" / "category.py",
        BASE / "app" / "models" / "order.py",
        BASE / "app" / "models" / "cart.py",
    ]
    for f in model_files:
        src = _src(f)
        # Should not have the old raw pattern
        assert "mapped_column(Uuid, default_factory=uuid7, primary_key=True)" not in src, (
            f"{f.name} still uses old uuid7 raw pattern"
        )
        # Should use uuid_id()
        assert "uuid_id()" in src, f"{f.name} does not use uuid_id()"


# ── TranslatableMixin in arvel.database.mixins ───────────────────────


def test_arvel_database_mixins_exists() -> None:
    assert ARVEL_DB_MIXINS.exists(), "arvel/database/mixins.py does not exist"


def test_translatable_mixin_in_arvel_database_mixins() -> None:
    assert ARVEL_DB_MIXINS.exists()
    src = _src(ARVEL_DB_MIXINS)
    assert "class TranslatableMixin" in src
    assert "def get_translation" in src
    assert "def set_translation" in src


def test_kit_base_re_exports_translatable_mixin() -> None:
    kit_base = BASE / "app" / "models" / "base.py"
    src = _src(kit_base)
    # Should import from arvel.database.mixins
    assert "arvel.database.mixins" in src or "arvel.database" in src


# ── Auth guards in arvel.auth.guards ─────────────────────────────────


def test_arvel_auth_guards_exists() -> None:
    assert ARVEL_AUTH_GUARDS.exists(), "arvel/auth/guards/__init__.py does not exist"


def test_arvel_auth_guards_exports() -> None:
    assert ARVEL_AUTH_GUARDS.exists()
    src = _src(ARVEL_AUTH_GUARDS)
    assert "async def require_auth" in src
    assert "make_permission_guard" in src
    assert "make_role_level_guard" in src


def test_arvel_auth_guards_lazy_permission_import() -> None:
    """arvel_permission must NOT be imported at module level in guards/__init__.py."""
    src = _src(ARVEL_AUTH_GUARDS)
    # Check that no top-level "import arvel_permission" or "from arvel_permission" exists
    # (lines beginning with 'import' or 'from' before the first function/class definition)
    lines = src.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("def ", "async def ", "class ")):
            break
        # Only flag actual import statements, not comments or docstrings
        if stripped.startswith(("import arvel_permission", "from arvel_permission")):
            raise AssertionError(
                f"arvel_permission imported at module level (line {i + 1}): {line}"
            )


def test_kit_deps_imports_guards_from_arvel() -> None:
    deps = BASE / "app" / "http" / "controllers" / "_deps.py"
    src = _src(deps)
    assert "arvel.auth.guards" in src


# ── Kit auth controller extends framework AuthController ─────────────


def test_kit_auth_controller_extends_framework_controller() -> None:
    """auth.py must extend arvel.auth.http.controller.AuthController, not re-implement it."""
    assert AUTH_CTRL.exists(), "app/http/controllers/auth.py is missing"
    src = _src(AUTH_CTRL)
    # Must import the framework's AuthController
    assert "arvel.auth.http.controller" in src
    # Must extend it
    assert "AuthController" in src
    # Must NOT re-implement login (that lives in the framework now)
    assert "async def login" not in src
    # Must NOT re-implement register
    assert "async def register" not in src


def test_routes_api_wires_auth_controller() -> None:
    src = _src(ROUTES_API)
    # Auth routes wired to a controller that's either the framework's or the kit's subclass
    assert "AuthController" in src or "EcommerceAuthController" in src


# ── CartItem and OrderItem use integer PK ────────────────────────────


def test_cart_item_id_is_integer() -> None:
    src = _src(CART_ITEM_MODEL)
    # After plain annotations are used — 'id: int = id_()'
    assert "    id: int" in src
    assert "id_(" in src


def test_order_item_id_is_integer() -> None:
    src = _src(ORDER_ITEM_MODEL)
    assert "    id: int" in src
    assert "id_(" in src


def test_migration_for_cart_items_pk_exists() -> None:
    # Greenfield project — PK is BIGSERIAL from the initial create migration, no ALTER needed.
    mig = BASE / "database" / "migrations" / "2026_05_23_000006_create_cart_items_table.py"
    assert mig.exists(), "cart_items create migration not found"
    src = mig.read_text()
    assert "t.id()" in src, "cart_items migration must use t.id() (BIGSERIAL)"
    assert "IdType.UUID" not in src, "cart_items must not use UUID PK"


def test_migration_for_order_items_pk_exists() -> None:
    # Greenfield project — PK is BIGSERIAL from the initial create migration, no ALTER needed.
    mig = BASE / "database" / "migrations" / "2026_05_23_000008_create_order_items_table.py"
    assert mig.exists(), "order_items create migration not found"
    src = mig.read_text()
    assert "t.id()" in src, "order_items migration must use t.id() (BIGSERIAL)"
    assert "IdType.UUID" not in src, "order_items must not use UUID PK"
