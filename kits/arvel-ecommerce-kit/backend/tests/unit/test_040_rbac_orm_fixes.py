"""RBAC ORM and serialization fixes.

Coverage:
  User.default_guard_name must be "api"
  bootstrap.py must use the shared refresh helper
  created_at serialised with .isoformat() in UserService and OrderService
  where_raw JSONB calls annotated with framework gap comment
  storefront_list composite cursor documents malformed-cursor handling
  CartService uses delete() not force_delete()
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


# ─── User.default_guard_name must be "api" ─────────────────────────────


class TestV011GuardName:
    """User.default_guard_name must equal 'api'."""

    def test_user_model_has_api_default_guard(self) -> None:
        src = _src(USER_MODEL_FILE)
        assert "default_guard_name" in src and '= "api"' in src, (
            "default_guard_name set to 'api' not found in user.py — "
            "all has_permission_to(str) checks silently fail with guard_name='web'"
        )

    def test_user_model_no_web_default_guard(self) -> None:
        src = _src(USER_MODEL_FILE)
        has_web = "default_guard_name" in src and '= "web"' in src
        assert not has_web, "default_guard_name='web' still present in user.py"


# ─── bootstrap.py must use the shared refresh helper ───────────────────


class TestV012BootstrapRefresh:
    """bootstrap.py must not use raw DB.statement REFRESH."""

    def test_bootstrap_no_raw_refresh_statement(self) -> None:
        src = _src(BOOTSTRAP_FILE)
        assert 'DB.statement("REFRESH MATERIALIZED VIEW products_catalog")' not in src, (
            "raw DB.statement REFRESH still in app/bootstrap.py"
        )

    def test_bootstrap_uses_refresh_view_orm(self) -> None:
        src = _src(BOOTSTRAP_FILE)
        assert "refresh_products_catalog" in src, (
            "shared refresh helper not called in app/bootstrap.py"
        )

    def test_bootstrap_imports_published_product(self) -> None:
        src = _src(BOOTSTRAP_FILE)
        assert "refresh_products_catalog" in src, (
            "shared refresh helper not imported in app/bootstrap.py"
        )


# ─── created_at serialized with .isoformat() ───────────────────────────


class TestV013DatetimeSerialization:
    """created_at must be serialized via .isoformat() on the same line."""

    def test_user_service_created_at_isoformat(self) -> None:
        src = _src(USER_SVC_FILE)
        lines = src.splitlines()
        for line in lines:
            if '"created_at"' in line and "created_at" in line:
                assert "isoformat" in line, (
                    f"created_at in UserService._format_user "
                    f"is not serialised with .isoformat() on the same line:\n  {line.strip()}"
                )
                return
        pytest.fail("'\"created_at\"' key not found in user_service.py")

    def test_order_service_created_at_isoformat(self) -> None:
        src = _src(ORDER_SVC_FILE)
        lines = src.splitlines()
        # Only match dict-assignment lines like `"created_at": order.created_at`
        for line in lines:
            if '"created_at"' in line and "order.created_at" in line:
                assert "isoformat" in line, (
                    f"created_at in OrderService._format_order "
                    f"is not serialised with .isoformat() on the same line:\n  {line.strip()}"
                )
                return
        pytest.fail("'\"created_at\": order.created_at' not found in order_service.py")


# ─── where_raw JSONB calls documented as framework gap ─────────────────


class TestV014JsonbGapDocumented:
    """JSONB where_raw calls must have a gap comment nearby."""

    def test_product_service_jsonb_where_raw_has_gap_comment(self) -> None:
        src = _src(PRODUCT_SVC_FILE)
        lines = src.splitlines()
        for i, line in enumerate(lines):
            if "where_raw" in line and "slug->>'en'" in line:
                # Gap comment must appear within 3 lines above
                preceding = "\n".join(lines[max(0, i - 3) : i + 1])
                assert "gap" in preceding.lower() or "G-001" in preceding, (
                    f"where_raw JSONB slug call at line {i + 1} "
                    f"has no framework gap comment. Preceding context:\n{preceding}"
                )


# ─── composite cursor gap note ─────────────────────────────────


class TestV015CursorGapDocumented:
    """storefront_list documents malformed-cursor handling."""

    def test_storefront_list_documents_malformed_cursor(self) -> None:
        src = _src(PRODUCT_SVC_FILE)
        assert "malformed cursor" in src.lower() and "InvalidCursorError" in src, (
            "storefront_list must document how a malformed cursor is handled "
            "(fall back to page one) in product_service.py"
        )


# ─── CartService uses delete() not force_delete() ──────────────────────


class TestV016CartItemDelete:
    """CartService must use delete() not force_delete()."""

    def test_cart_service_no_force_delete(self) -> None:
        src = _src(CART_SVC_FILE)
        assert "force_delete" not in src, (
            "force_delete() still present in cart_service.py — "
            "CartItem has no SoftDeletes, use delete() instead"
        )

    def test_cart_service_uses_delete(self) -> None:
        src = _src(CART_SVC_FILE)
        assert "await item.delete()" in src, "await item.delete() not found in cart_service.py"
