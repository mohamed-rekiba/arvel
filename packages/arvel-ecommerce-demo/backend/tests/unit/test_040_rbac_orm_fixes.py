"""WI-arvel-040 — RED tests for V-011 through V-016.

All tests must FAIL before fixes (RED state).
They turn GREEN after Stage 3b execution.

Coverage:
  V-011 — User.default_guard_name must be "api"
  V-012 — bootstrap.py must use the shared refresh helper
  V-013 — created_at serialised with .isoformat() in UserService and OrderService
  V-014 — where_raw JSONB calls annotated with framework gap comment
  V-015 — storefront_list composite cursor references G-002
  V-016 — CartService uses delete() not force_delete()
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Source file helpers — no framework import needed.
_BACKEND = Path(__file__).parents[2]

USER_MODEL_FILE = _BACKEND / "app" / "models" / "user.py"
BOOTSTRAP_FILE = _BACKEND / "app" / "bootstrap.py"
USER_SVC_FILE = _BACKEND / "app" / "services" / "user_service.py"
ORDER_SVC_FILE = _BACKEND / "app" / "services" / "order_service.py"
PRODUCT_SVC_FILE = _BACKEND / "app" / "services" / "product_service.py"
CART_SVC_FILE = _BACKEND / "app" / "services" / "cart_service.py"


def _src(path: Path) -> str:
    return path.read_text()


# ─── V-011: User.default_guard_name must be "api" ─────────────────────────────


class TestV011GuardName:
    """AC-001a-c: User.default_guard_name must equal 'api'."""

    def test_user_model_has_api_default_guard(self) -> None:
        src = _src(USER_MODEL_FILE)
        assert 'default_guard_name = "api"' in src or 'default_guard_name: str = "api"' in src, (
            "V-011 not fixed: default_guard_name set to 'api' not found in user.py — "
            "all has_permission_to(str) checks silently fail with guard_name='web'"
        )

    def test_user_model_no_web_default_guard(self) -> None:
        src = _src(USER_MODEL_FILE)
        has_web = 'default_guard_name = "web"' in src or 'default_guard_name: str = "web"' in src
        assert not has_web, "V-011 not fixed: default_guard_name='web' still present in user.py"


# ─── V-012: bootstrap.py must use the shared refresh helper ───────────────────


class TestV012BootstrapRefresh:
    """AC-002a-b: bootstrap.py must not use raw DB.statement REFRESH."""

    def test_bootstrap_no_raw_refresh_statement(self) -> None:
        src = _src(BOOTSTRAP_FILE)
        assert 'DB.statement("REFRESH MATERIALIZED VIEW products_catalog")' not in src, (
            "V-012 not fixed: raw DB.statement REFRESH still in app/bootstrap.py"
        )

    def test_bootstrap_uses_refresh_view_orm(self) -> None:
        src = _src(BOOTSTRAP_FILE)
        assert "refresh_products_catalog" in src, (
            "V-012 not fixed: shared refresh helper not called in app/bootstrap.py"
        )

    def test_bootstrap_imports_published_product(self) -> None:
        src = _src(BOOTSTRAP_FILE)
        assert "refresh_products_catalog" in src, (
            "V-012 not fixed: shared refresh helper not imported in app/bootstrap.py"
        )


# ─── V-013: created_at serialized with .isoformat() ───────────────────────────


class TestV013DatetimeSerialization:
    """AC-003a-b: created_at must be serialized via .isoformat() on the same line."""

    def test_user_service_created_at_isoformat(self) -> None:
        src = _src(USER_SVC_FILE)
        lines = src.splitlines()
        for line in lines:
            if '"created_at"' in line and "created_at" in line:
                assert "isoformat" in line, (
                    f"V-013 not fixed: created_at in UserService._format_user "
                    f"is not serialised with .isoformat() on the same line:\n  {line.strip()}"
                )
                return
        pytest.fail("V-013: '\"created_at\"' key not found in user_service.py")

    def test_order_service_created_at_isoformat(self) -> None:
        src = _src(ORDER_SVC_FILE)
        lines = src.splitlines()
        # Only match dict-assignment lines like `"created_at": order.created_at`
        for line in lines:
            if '"created_at"' in line and "order.created_at" in line:
                assert "isoformat" in line, (
                    f"V-013 not fixed: created_at in OrderService._format_order "
                    f"is not serialised with .isoformat() on the same line:\n  {line.strip()}"
                )
                return
        pytest.fail("V-013: '\"created_at\": order.created_at' not found in order_service.py")


# ─── V-014: where_raw JSONB calls documented as framework gap ─────────────────


class TestV014JsonbGapDocumented:
    """AC-004a: JSONB where_raw calls must have a gap comment nearby."""

    def test_product_service_jsonb_where_raw_has_gap_comment(self) -> None:
        src = _src(PRODUCT_SVC_FILE)
        lines = src.splitlines()
        for i, line in enumerate(lines):
            if "where_raw" in line and "slug->>'en'" in line:
                # Gap comment must appear within 3 lines above
                preceding = "\n".join(lines[max(0, i - 3) : i + 1])
                assert "gap" in preceding.lower() or "G-001" in preceding, (
                    f"V-014 not fixed: where_raw JSONB slug call at line {i + 1} "
                    f"has no framework gap comment. Preceding context:\n{preceding}"
                )


# ─── V-015: composite cursor references G-002 ─────────────────────────────────


class TestV015CursorGapDocumented:
    """AC-005a: storefront_list must reference G-002."""

    def test_storefront_list_references_g002(self) -> None:
        src = _src(PRODUCT_SVC_FILE)
        assert "G-002" in src, (
            "V-015 not fixed: G-002 framework gap reference not found in product_service.py"
        )


# ─── V-016: CartService uses delete() not force_delete() ──────────────────────


class TestV016CartItemDelete:
    """AC-006a-b: CartService must use delete() not force_delete()."""

    def test_cart_service_no_force_delete(self) -> None:
        src = _src(CART_SVC_FILE)
        assert "force_delete" not in src, (
            "V-016 not fixed: force_delete() still present in cart_service.py — "
            "CartItem has no SoftDeletes, use delete() instead"
        )

    def test_cart_service_uses_delete(self) -> None:
        src = _src(CART_SVC_FILE)
        assert "await item.delete()" in src, (
            "V-016 not fixed: await item.delete() not found in cart_service.py"
        )
