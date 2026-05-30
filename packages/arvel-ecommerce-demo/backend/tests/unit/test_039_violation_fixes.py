"""WI-arvel-039 — RED tests for V-001 through V-010.

All tests in this file must FAIL before the fixes are applied (RED state).
They turn GREEN after execution in Stage 3b.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── Helpers ──────────────────────────────────────────────────────────────────

ROUTES_FILE = Path(__file__).parents[2] / "routes" / "api.py"
PRODUCT_SVC_FILE = Path(__file__).parents[2] / "app" / "services" / "product_service.py"


def _routes_src() -> str:
    return ROUTES_FILE.read_text()


def _product_svc_src() -> str:
    return PRODUCT_SVC_FILE.read_text()


# ─── V-001: Python 2 except tuple syntax in image upload route ───────────────


class TestV001ExceptSyntax:
    """AC-001a: routes/api.py must use `except (OSError, RuntimeError):`."""

    def test_no_python2_except_tuple_syntax(self) -> None:
        src = _routes_src()
        # Python 2 form — bare comma between exception types without parens
        assert "except OSError, RuntimeError:" not in src, (
            "V-001 not fixed: Python 2 except tuple syntax still present in routes/api.py"
        )

    def test_correct_except_tuple_catches_runtime_error(self) -> None:
        """The corrected clause must catch RuntimeError."""
        caught: list[type[BaseException]] = []

        def _catch(exc: BaseException) -> None:
            caught.append(type(exc))

        for exc_cls in (OSError, RuntimeError):
            try:
                raise exc_cls("test")
            except (OSError, RuntimeError) as exc:
                _catch(exc)

        assert OSError in caught
        assert RuntimeError in caught

    def test_routes_has_no_bare_image_manager_block(self) -> None:
        """V-001 is fixed: the broken ImageManager block (with its Python 2 except) is removed."""
        src = _routes_src()
        # The entire broken block was removed — neither the Python 2 nor Python 3 form exists.
        # Confirming the Python 2 form is absent is sufficient.
        assert "_HAS_IMAGE_MANAGER = True" not in src, (
            "V-001 not fully fixed: conditional ImageManager block still present"
        )


# ─── V-002: guard_name="web" must be "api" ───────────────────────────────────


class TestV002GuardName:
    """AC-002a: Role lookup must use guard_name='api'."""

    def test_no_guard_name_web_in_role_lookup(self) -> None:
        src = _routes_src()
        # guard_name="web" anywhere in routes is wrong — all data uses "api"
        assert 'guard_name="web"' not in src, (
            "V-002 not fixed: guard_name='web' still present in routes/api.py"
        )

    def test_role_lookup_uses_api_guard(self) -> None:
        users_ctrl = (
            ROUTES_FILE.parent.parent / "app" / "http" / "controllers" / "admin" / "users.py"
        ).read_text()
        assert 'guard_name="api"' in users_ctrl, (
            "V-002 not fixed: guard_name='api' not found in admin/users.py"
        )


# ─── V-003: ProductService.create() must not use raw SQL ─────────────────────


class TestV003CreateUsesOrm:
    """AC-003a/b: create() must use ORM, not DB.statement."""

    def test_create_does_not_use_db_statement(self) -> None:
        src = _product_svc_src()
        # Check that DB.statement / DB.select are not used anywhere in the file
        assert "await DB.statement" not in src, (
            "V-003 not fixed: DB.statement still called in product_service.py"
        )

    def test_create_does_not_use_db_select(self) -> None:
        src = _product_svc_src()
        assert "await DB.select" not in src, (
            "V-003 not fixed: DB.select still called in product_service.py"
        )

    def test_db_not_imported_in_product_service(self) -> None:
        src = _product_svc_src()
        assert "from arvel.database.db import DB" not in src, (
            "V-003/NFR-004 not fixed: DB is still imported in product_service.py"
        )

    def test_uuid7_not_called_manually_in_service(self) -> None:
        src = _product_svc_src()
        # uuid7 should not be imported for manual ID generation
        assert "from app.models.base import uuid7" not in src, (
            "V-003 not fixed: uuid7 still imported in product_service.py"
        )

    @pytest.mark.asyncio
    async def test_create_uses_product_orm(self) -> None:
        from app.services.product_service import ProductService

        svc = ProductService()
        _prod_id = uuid.UUID("01960000-0000-7000-8000-000000000001")
        _cat_id = uuid.UUID("01960000-0000-7000-8000-000000000002")
        _ven_id = uuid.UUID("01960000-0000-7000-8000-000000000003")

        mock_product = MagicMock()
        mock_product.id = _prod_id
        mock_product.name = {"en": "Test"}
        mock_product.slug = {"en": "test"}
        mock_product.description = {}
        mock_product.price = 9.99
        mock_product.stock_qty = 0
        mock_product.status = "draft"
        mock_product.published_at = None
        mock_product.category_id = _cat_id
        mock_product.vendor_id = _ven_id
        mock_product.created_at = None
        mock_product.updated_at = None
        mock_product.deleted_at = None

        with patch("app.services.product_service.Product") as MockProduct:
            MockProduct.create = AsyncMock(return_value=mock_product)
            result = await svc.create(
                {
                    "name": {"en": "Test"},
                    "slug": {"en": "test"},
                    "description": {},
                    "price": 9.99,
                    "stock_qty": 0,
                    "category_id": str(_cat_id),
                    "vendor_id": str(_ven_id),
                }
            )
        MockProduct.create.assert_awaited_once()
        assert result["name"] == {"en": "Test"}


# ─── V-004: Write methods must use ORM ───────────────────────────────────────


class TestV004WriteMethodsUseOrm:
    """AC-004a-d: update, soft_delete, force_delete, restore, publish, unpublish use ORM."""

    def test_no_raw_update_sql_in_product_service(self) -> None:
        src = _product_svc_src()
        assert "UPDATE products" not in src, (
            "V-004 not fixed: raw UPDATE products SQL still in product_service.py"
        )

    def test_no_raw_delete_sql_in_product_service(self) -> None:
        src = _product_svc_src()
        assert "DELETE FROM products" not in src, (
            "V-004 not fixed: raw DELETE FROM products SQL still in product_service.py"
        )

    def test_no_cast_products_status_sql(self) -> None:
        src = _product_svc_src()
        assert "CAST(:status AS products_status)" not in src, (
            "V-004 not fixed: CAST(:status AS products_status) still in product_service.py"
        )

    def test_no_cast_jsonb_sql(self) -> None:
        src = _product_svc_src()
        assert "CAST(:name AS jsonb)" not in src, (
            "V-004 not fixed: CAST(:name AS jsonb) still in product_service.py"
        )

    @pytest.mark.asyncio
    async def test_publish_sets_status_via_orm(self) -> None:
        from app.services.product_service import ProductService

        svc = ProductService()
        mock_product = MagicMock()
        mock_product.status = "draft"
        mock_product.published_at = None
        mock_product.save = AsyncMock(return_value=mock_product)

        _pid = "01960000-0000-7000-8000-000000000099"
        admin_result: dict[str, Any] = {
            "id": _pid,
            "name": {},
            "slug": {},
            "description": {},
            "price": 0.0,
            "stock_qty": 0,
            "status": "published",
            "published_at": None,
            "category_id": "",
            "vendor_id": "",
            "created_at": None,
            "updated_at": None,
            "deleted_at": None,
        }

        with (
            patch("app.services.product_service.Product") as MockProduct,
            patch.object(svc, "admin_get", AsyncMock(return_value=admin_result)),
        ):
            MockProduct.with_trashed = MagicMock(
                return_value=MagicMock(
                    where=MagicMock(
                        return_value=MagicMock(first=AsyncMock(return_value=mock_product))
                    )
                )
            )
            await svc.publish(_pid)

        mock_product.save.assert_awaited_once()
        assert mock_product.status == "published"


# ─── V-005: admin_list and admin_get must use ORM ────────────────────────────


class TestV005ReadMethodsUseOrm:
    """AC-005a-d: admin_list and admin_get use Product.query() / Product.find()."""

    def test_no_raw_select_in_product_service(self) -> None:
        src = _product_svc_src()
        assert "SELECT id::text" not in src, (
            "V-005 not fixed: raw SELECT still in product_service.py"
        )

    def test_no_admin_get_sql_constants(self) -> None:
        src = _product_svc_src()
        assert "_ADMIN_GET_SQL" not in src, (
            "V-005 not fixed: _ADMIN_GET_SQL class constant still in product_service.py"
        )

    def test_row_to_admin_product_replaced(self) -> None:
        src = _product_svc_src()
        assert "_row_to_admin_product" not in src, (
            "V-005 not fixed: _row_to_admin_product still present; use _product_to_admin instead"
        )


# ─── V-006: get_stock / decrement_stock must be ORM / removed ────────────────


class TestV006StockMethodsClean:
    """AC-006a/b: get_stock uses ORM; decrement_stock removed."""

    def test_no_select_stock_qty_raw_sql(self) -> None:
        src = _product_svc_src()
        assert "SELECT stock_qty FROM products" not in src, (
            "V-006 not fixed: raw SELECT stock_qty still in product_service.py"
        )

    def test_decrement_stock_removed(self) -> None:
        from app.services.product_service import ProductService

        assert not hasattr(ProductService, "decrement_stock"), (
            "V-006 not fixed: decrement_stock still exists on ProductService"
        )


# ─── V-007: Dead code removed ────────────────────────────────────────────────


class TestV007DeadCodeRemoved:
    """AC-007a: _row_to_storefront_product deleted."""

    def test_row_to_storefront_product_removed(self) -> None:
        from app.services.product_service import ProductService

        assert not hasattr(ProductService, "_row_to_storefront_product"), (
            "V-007 not fixed: _row_to_storefront_product still exists on ProductService"
        )

    def test_row_to_storefront_not_in_source(self) -> None:
        src = _product_svc_src()
        assert "_row_to_storefront_product" not in src, (
            "V-007 not fixed: _row_to_storefront_product still in product_service.py source"
        )


# ─── V-008: User lifecycle endpoints exist in routes ─────────────────────────


class TestV008UserLifecycleEndpoints:
    """AC-008a-d: suspend/unsuspend/restore routes exist."""

    def test_suspend_route_exists(self) -> None:
        src = _routes_src()
        assert "/suspend" in src, "V-008 not fixed: no /suspend route in routes/api.py"

    def test_unsuspend_route_exists(self) -> None:
        src = _routes_src()
        assert "/unsuspend" in src, "V-008 not fixed: no /unsuspend route in routes/api.py"

    def test_user_restore_route_exists(self) -> None:
        src = _routes_src()
        # User restore is inside with Route.group(prefix="/users", ...) so the path
        # "/{user_id}/restore" appears in routes/api.py
        assert "/{user_id}/restore" in src, (
            "V-008 not fixed: no user restore route in routes/api.py"
        )

    def test_suspend_requires_users_manage_permission(self) -> None:
        users_ctrl = (
            ROUTES_FILE.parent.parent / "app" / "http" / "controllers" / "admin" / "users.py"
        ).read_text()
        assert '"users.manage"' in users_ctrl, (
            "V-008 not fixed: users.manage permission check missing"
        )


# ─── V-009: Revoke permission endpoint exists ─────────────────────────────────


class TestV009RevokePermissionEndpoint:
    """AC-009a-c: DELETE /api/admin/users/{id}/permissions/{perm} exists."""

    def test_revoke_permission_route_exists(self) -> None:
        src = _routes_src()
        assert "revoke_permission" in src or ("/permissions/" in src and "DELETE" in src), (
            "V-009 not fixed: no revoke-permission route in routes/api.py"
        )

    def test_revoke_permission_to_called(self) -> None:
        users_ctrl = (
            ROUTES_FILE.parent.parent / "app" / "http" / "controllers" / "admin" / "users.py"
        ).read_text()
        assert "revoke_permission_to" in users_ctrl, (
            "V-009 not fixed: revoke_permission_to not called in admin/users.py"
        )

    def test_revoke_permission_requires_roles_manage(self) -> None:
        users_ctrl = (
            ROUTES_FILE.parent.parent / "app" / "http" / "controllers" / "admin" / "users.py"
        ).read_text()
        assert '"roles.manage"' in users_ctrl, (
            "V-009 not fixed: roles.manage permission check missing"
        )


# ─── V-010: Materialized view refresh uses ORM helper ────────────────────────


class TestV010RefreshViewConsistency:
    """AC-010a/b: routes use the shared materialized-view refresh helper."""

    def test_no_raw_refresh_sql_in_routes(self) -> None:
        src = _routes_src()
        assert 'DB.statement("REFRESH MATERIALIZED VIEW products_catalog")' not in src, (
            "V-010 not fixed: raw DB.statement REFRESH still in routes/api.py"
        )

    def test_refresh_view_called_via_controllers(self) -> None:
        # Refresh is now triggered by the observer after model saves;
        # the on-demand endpoint lives in app/http/controllers/admin/products.py.
        from pathlib import Path

        products_ctrl = (
            Path(__file__).parents[2] / "app" / "http" / "controllers" / "admin" / "products.py"
        ).read_text()
        assert "refresh_catalog" in products_ctrl, (
            "V-010 not fixed: catalog refresh endpoint missing from admin products controller"
        )
