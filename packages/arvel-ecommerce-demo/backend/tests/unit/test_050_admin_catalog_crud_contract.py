"""Admin catalog CRUD route contracts — verifies the refactored architecture."""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).parents[2]
API_ROUTES = BASE_DIR / "routes" / "api.py"
ORDER_SERVICE = BASE_DIR / "app" / "services" / "order_service.py"
CATEGORIES_CTRL = BASE_DIR / "app" / "http" / "controllers" / "admin" / "categories.py"
VENDORS_CTRL = BASE_DIR / "app" / "http" / "controllers" / "admin" / "vendors.py"
PRODUCTS_CTRL = BASE_DIR / "app" / "http" / "controllers" / "admin" / "products.py"
ORDERS_CTRL = BASE_DIR / "app" / "http" / "controllers" / "admin" / "orders.py"
CATEGORY_SERVICE = BASE_DIR / "app" / "services" / "category_service.py"
VENDOR_SERVICE = BASE_DIR / "app" / "services" / "vendor_service.py"


def _src(path: Path) -> str:
    return path.read_text()


def test_admin_category_crud_routes_are_wired() -> None:
    """Routes live in routes/api.py; controllers hold the handler logic."""
    routes = _src(API_ROUTES)
    ctrl = _src(CATEGORIES_CTRL)

    # Routes declared in routes/api.py with controller= pattern
    for snippet in (
        "controller=AdminCategoriesController",
        '"/categories"',
        '"/{category_id}"',
        '"/{category_id}/publish"',
        '"/{category_id}/unpublish"',
        '"/{category_id}/restore"',
        '"/{category_id}/force"',
    ):
        assert snippet in routes, f"Expected {snippet!r} in routes/api.py"

    # Permission checks live in the controller, not routes
    for permission in (
        'require_permission(request, "categories.create")',
        'require_permission(request, "categories.update")',
        'require_permission(request, "categories.delete")',
        'require_role_level(request, "categories.delete", 100)',
    ):
        assert permission in ctrl, f"Expected {permission!r} in categories controller"


def test_admin_vendor_crud_routes_are_wired() -> None:
    """Routes live in routes/api.py; controllers hold the handler logic."""
    routes = _src(API_ROUTES)
    ctrl = _src(VENDORS_CTRL)

    for snippet in (
        "controller=AdminVendorsController",
        '"/vendors"',
        '"/{vendor_id}"',
        '"/{vendor_id}/publish"',
        '"/{vendor_id}/unpublish"',
        '"/{vendor_id}/restore"',
        '"/{vendor_id}/force"',
    ):
        assert snippet in routes, f"Expected {snippet!r} in routes/api.py"

    for permission in (
        'require_permission(request, "vendors.create")',
        'require_permission(request, "vendors.update")',
        'require_permission(request, "vendors.delete")',
        'require_role_level(request, "vendors.delete", 100)',
    ):
        assert permission in ctrl, f"Expected {permission!r} in vendors controller"


def test_catalog_mutations_trigger_observer_refresh() -> None:
    """Refresh is handled by ProductsCatalogRefreshObserver, not background_tasks."""
    observer_file = BASE_DIR / "app" / "observers" / "products_catalog_refresh_observer.py"
    src = observer_file.read_text()
    assert "refresh_products_catalog" in src
    assert "ProductsCatalogRefreshObserver" in src

    # On-demand refresh endpoint must exist in the products controller
    products_ctrl = _src(PRODUCTS_CTRL)
    assert "catalog_refresh" in products_ctrl
    assert "refresh_catalog" in products_ctrl

    # The force_destroy permission check lives in the products controller
    assert 'require_role_level(request, "products.delete", 100)' in products_ctrl


def test_catalog_serializers_use_service_layer() -> None:
    """Serialization logic lives in CategoryService / VendorService, not inline in routes."""
    cat_svc = _src(CATEGORY_SERVICE)
    ven_svc = _src(VENDOR_SERVICE)

    assert "deleted_at" in cat_svc
    assert "deleted_at" in ven_svc
    assert "def to_dict" in cat_svc
    assert "def to_dict" in ven_svc


def test_category_vendor_indexes_honor_trashed_filter() -> None:
    """Trashed filtering is a typed query param on the controller index, surfaced in
    the OpenAPI spec, and passed straight to the service's list()."""
    cat_ctrl = _src(CATEGORIES_CTRL)
    ven_ctrl = _src(VENDORS_CTRL)
    cat_svc = _src(CATEGORY_SERVICE)
    ven_svc = _src(VENDOR_SERVICE)

    # trashed is a typed Literal query param on the controller (shows up in the spec).
    typed_param = 'trashed: Literal["without", "with", "only"]'
    assert typed_param in cat_ctrl, "Expected typed trashed param in categories controller"
    assert typed_param in ven_ctrl, "Expected typed trashed param in vendors controller"

    # The service's list() accepts the three trashed modes as a typed parameter.
    for snippet in ('"without"', '"with"', '"only"'):
        assert snippet in cat_svc, f"Expected {snippet!r} in CategoryService"
        assert snippet in ven_svc, f"Expected {snippet!r} in VendorService"


def test_admin_read_metadata_routes_are_wired() -> None:
    """Key admin read routes are declared in routes/api.py."""
    routes = _src(API_ROUTES)

    for snippet in (
        "controller=AdminProductsController",
        "controller=AdminRolesController",
        "controller=AdminTranslationsController",
    ):
        assert snippet in routes, f"Expected {snippet!r} in routes/api.py"

    # Permission checks are in the controllers
    products_ctrl = _src(PRODUCTS_CTRL)
    assert 'require_permission(request, "products.view")' in products_ctrl

    roles_ctrl = _src(BASE_DIR / "app" / "http" / "controllers" / "admin" / "roles.py")
    assert 'require_permission(request, "roles.manage")' in roles_ctrl

    cats_ctrl = _src(CATEGORIES_CTRL)
    assert 'require_permission(request, "categories.view")' in cats_ctrl


def test_admin_order_status_route_validates_status_payload() -> None:
    """Order status update goes through a validated Pydantic payload."""
    orders_ctrl = _src(ORDERS_CTRL)
    service = _src(ORDER_SERVICE)
    routes = _src(API_ROUTES)

    assert "controller=AdminOrdersController" in routes
    assert '"/{order_id}/status"' in routes

    assert 'require_permission(request, "orders.update")' in orders_ctrl
    assert "UpdateOrderStatusPayload" in orders_ctrl
    assert "except InvalidOrderStatusTransitionError" in orders_ctrl

    assert "class InvalidOrderStatusTransitionError(Exception)" in service
    assert "def _can_transition(current: str, target: str) -> bool" in service
    assert "async def _restore_stock_for_order" in service
    assert 'status == "cancelled"' in service
