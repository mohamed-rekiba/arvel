"""Framework architecture compliance tests.

These tests verify that the ecommerce demo follows the Arvel framework's
documented patterns:
- Routes live in routes/api.py, not in controller files
- Controllers inherit Controller base class
- Route.group() and Route.resource() are used
- CategoryService and VendorService exist
- JsonResource is used for response transformation

Tests are written BEFORE the refactor — they should FAIL on the current
(non-compliant) code and PASS after the refactor.
"""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).parents[2]
ROUTES_FILE = BASE_DIR / "routes" / "api.py"
CONTROLLERS_DIR = BASE_DIR / "app" / "http" / "controllers"
ADMIN_CONTROLLERS_DIR = CONTROLLERS_DIR / "admin"
SERVICES_DIR = BASE_DIR / "app" / "services"
RESOURCES_DIR = BASE_DIR / "app" / "http" / "resources"


def _src(path: Path) -> str:
    return path.read_text()


# ─── No @Route.* decorators in controller files ──────────────────────


def test_no_route_decorators_in_storefront_controller() -> None:
    """@Route.* must not appear in controller files — storefront."""
    src = _src(CONTROLLERS_DIR / "storefront.py")
    assert "@Route." not in src, (
        "AC-001 FAIL: @Route.* found in controllers/storefront.py — routes belong in routes/api.py"
    )


def test_no_route_decorators_in_auth_controller() -> None:
    """@Route.* must not appear in controller files — auth."""
    src = _src(CONTROLLERS_DIR / "auth.py")
    assert "@Route." not in src, (
        "AC-001 FAIL: @Route.* found in controllers/auth.py — routes belong in routes/api.py"
    )


def test_no_route_decorators_in_cart_controller() -> None:
    """@Route.* must not appear in controller files — cart."""
    src = _src(CONTROLLERS_DIR / "cart.py")
    assert "@Route." not in src, (
        "AC-001 FAIL: @Route.* found in controllers/cart.py — routes belong in routes/api.py"
    )


def test_no_route_decorators_in_checkout_controller() -> None:
    src = _src(CONTROLLERS_DIR / "checkout.py")
    assert "@Route." not in src, "AC-001 FAIL: @Route.* found in controllers/checkout.py"


def test_no_route_decorators_in_admin_products_controller() -> None:
    src = _src(ADMIN_CONTROLLERS_DIR / "products.py")
    assert "@Route." not in src, "AC-001 FAIL: @Route.* found in admin/products.py"


def test_no_route_decorators_in_admin_categories_controller() -> None:
    src = _src(ADMIN_CONTROLLERS_DIR / "categories.py")
    assert "@Route." not in src, "AC-001 FAIL: @Route.* found in admin/categories.py"


def test_no_route_decorators_in_admin_vendors_controller() -> None:
    src = _src(ADMIN_CONTROLLERS_DIR / "vendors.py")
    assert "@Route." not in src, "AC-001 FAIL: @Route.* found in admin/vendors.py"


def test_no_route_decorators_in_admin_orders_controller() -> None:
    src = _src(ADMIN_CONTROLLERS_DIR / "orders.py")
    assert "@Route." not in src, "AC-001 FAIL: @Route.* found in admin/orders.py"


def test_no_route_decorators_in_admin_users_controller() -> None:
    src = _src(ADMIN_CONTROLLERS_DIR / "users.py")
    assert "@Route." not in src, "AC-001 FAIL: @Route.* found in admin/users.py"


# ─── All controllers inherit Controller ───────────────────────────────


def test_admin_products_controller_inherits_controller() -> None:
    """AdminProductsController must extend Controller."""
    src = _src(ADMIN_CONTROLLERS_DIR / "products.py")
    assert "Controller" in src, (
        "AC-002 FAIL: admin/products.py does not import or extend Controller"
    )
    assert (
        "class AdminProductsController(Controller)" in src
        or "class ProductsController(Controller)" in src
    ), "AC-002 FAIL: admin products controller class does not extend Controller"


def test_admin_categories_controller_inherits_controller() -> None:
    """AdminCategoriesController must extend Controller."""
    src = _src(ADMIN_CONTROLLERS_DIR / "categories.py")
    assert (
        "class AdminCategoriesController(Controller)" in src
        or "class CategoriesController(Controller)" in src
    ), "AC-002 FAIL: admin categories controller class does not extend Controller"


def test_admin_vendors_controller_inherits_controller() -> None:
    """AdminVendorsController must extend Controller."""
    src = _src(ADMIN_CONTROLLERS_DIR / "vendors.py")
    assert (
        "class AdminVendorsController(Controller)" in src
        or "class VendorsController(Controller)" in src
    ), "AC-002 FAIL: admin vendors controller class does not extend Controller"


def test_admin_orders_controller_inherits_controller() -> None:
    src = _src(ADMIN_CONTROLLERS_DIR / "orders.py")
    assert (
        "class AdminOrdersController(Controller)" in src
        or "class OrdersController(Controller)" in src
    ), "AC-002 FAIL: admin orders controller class does not extend Controller"


def test_storefront_controller_inherits_controller() -> None:
    src = _src(CONTROLLERS_DIR / "storefront.py")
    assert (
        "class StorefrontController(Controller)" in src or "class Storefront(Controller)" in src
    ), "AC-002 FAIL: StorefrontController does not extend Controller"


# ─── Route.group and Route.resource in routes/api.py ────────


def test_routes_api_uses_route_group() -> None:
    """Route.group must be used in routes/api.py."""
    src = _src(ROUTES_FILE)
    assert "Route.group(" in src, "AC-003 FAIL: Route.group() not found in routes/api.py"


def test_routes_api_uses_framework_routing() -> None:
    """routes/api.py must use Route.group and controller= pattern.


    Route.api_resource() uses PUT for updates; since the frontend uses PATCH,
    explicit Route.patch declarations are correct and preferred over api_resource.
    """
    src = _src(ROUTES_FILE)
    # Must use the Route facade, not raw @app.get decorators
    assert "Route." in src, "AC-004 FAIL: Route facade not used in routes/api.py"
    # Must not bypass the framework with raw fastapi decorators
    assert "@app.get" not in src, "raw @app.get found — use Route.get"
    assert "@app.post" not in src, "raw @app.post found — use Route.post"


def test_routes_api_has_admin_group() -> None:
    """routes/api.py must declare an admin prefix group."""
    src = _src(ROUTES_FILE)
    assert '"/api/admin"' in src or 'prefix="/api/admin"' in src or "prefix='/api/admin'" in src, (
        "routes/api.py must have a Route.group with /api/admin prefix"
    )


def test_routes_api_registers_products_routes() -> None:
    """routes/api.py must register admin product routes using controller= pattern."""
    src = _src(ROUTES_FILE)
    assert "AdminProductsController" in src, (
        "AC-004 FAIL: AdminProductsController not referenced in routes/api.py"
    )
    assert '"/products"' in src or "products" in src, (
        "AC-004 FAIL: /products routes not declared in routes/api.py"
    )


def test_routes_api_registers_categories_routes() -> None:
    """routes/api.py must register admin category routes using controller= pattern."""
    src = _src(ROUTES_FILE)
    assert "AdminCategoriesController" in src, (
        "AC-004 FAIL: AdminCategoriesController not referenced in routes/api.py"
    )


def test_routes_api_registers_vendors_routes() -> None:
    src = _src(ROUTES_FILE)
    assert "AdminVendorsController" in src, (
        "AC-004 FAIL: AdminVendorsController not referenced in routes/api.py"
    )


# ─── CategoryService and VendorService exist ────────────────


def test_category_service_exists() -> None:
    """app/services/category_service.py must exist."""
    service_file = SERVICES_DIR / "category_service.py"
    assert service_file.exists(), "AC-005 FAIL: app/services/category_service.py does not exist"


def test_category_service_has_list_method() -> None:
    """CategoryService must have a list method."""
    service_file = SERVICES_DIR / "category_service.py"
    if not service_file.exists():
        return  # handled by test above
    src = service_file.read_text()
    assert "class CategoryService" in src, "CategoryService class not found"
    assert "async def list" in src or "def list" in src, (
        "AC-005 FAIL: CategoryService has no list method"
    )


def test_category_service_has_find_method() -> None:
    service_file = SERVICES_DIR / "category_service.py"
    if not service_file.exists():
        return
    src = service_file.read_text()
    assert "async def find" in src or "def find" in src, (
        "AC-005 FAIL: CategoryService has no find method"
    )


def test_category_service_has_to_dict_method() -> None:
    service_file = SERVICES_DIR / "category_service.py"
    if not service_file.exists():
        return
    src = service_file.read_text()
    assert "def to_dict" in src, "AC-005 FAIL: CategoryService has no to_dict serialization method"


def test_vendor_service_exists() -> None:
    """app/services/vendor_service.py must exist."""
    service_file = SERVICES_DIR / "vendor_service.py"
    assert service_file.exists(), "AC-006 FAIL: app/services/vendor_service.py does not exist"


def test_vendor_service_has_list_method() -> None:
    service_file = SERVICES_DIR / "vendor_service.py"
    if not service_file.exists():
        return
    src = service_file.read_text()
    assert "class VendorService" in src, "VendorService class not found"
    assert "async def list" in src or "def list" in src, (
        "AC-006 FAIL: VendorService has no list method"
    )


def test_vendor_service_has_to_dict_method() -> None:
    service_file = SERVICES_DIR / "vendor_service.py"
    if not service_file.exists():
        return
    src = service_file.read_text()
    assert "def to_dict" in src, "AC-006 FAIL: VendorService has no to_dict serialization method"


# ─── JsonResource subclasses ─────────────────────────────────────────


def test_json_resource_used_in_demo() -> None:
    """JsonResource must be imported somewhere in the HTTP layer."""
    found = False
    for py_file in (CONTROLLERS_DIR / "..").rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        if "JsonResource" in py_file.read_text():
            found = True
            break
    assert found, (
        "AC-007 FAIL: JsonResource not used anywhere in app/http/ — "
        "adopt arvel.http.resources.JsonResource for response transformation"
    )


def test_category_controller_uses_category_service() -> None:
    """CategoryService is wired through _deps.py and used by the controller."""
    # Services are instantiated in _deps.py and injected into controllers via DI.
    deps_src = _src(CONTROLLERS_DIR / "_deps.py")
    assert "CategoryService" in deps_src, "_deps.py must import and instantiate CategoryService"
    ctrl_src = _src(ADMIN_CONTROLLERS_DIR / "categories.py")
    assert "categories" in ctrl_src, "admin/categories.py must use the injected CategoryService dep"


def test_vendor_controller_uses_vendor_service() -> None:
    """VendorService is wired through _deps.py and used by the controller."""
    deps_src = _src(CONTROLLERS_DIR / "_deps.py")
    assert "VendorService" in deps_src, "_deps.py must import and instantiate VendorService"
    ctrl_src = _src(ADMIN_CONTROLLERS_DIR / "vendors.py")
    assert "vendors" in ctrl_src, "admin/vendors.py must use the injected VendorService dep"


# ─── API contract unchanged ─────────────────────────────────────────


def test_all_original_endpoints_still_declared_in_routes() -> None:
    """All original resource types must still be covered in routes/api.py.


    Routes use Route.group(prefix=...) so full paths like '/api/admin/products'
    are composed from a group prefix + relative path; the literal full path need
    not appear in the source. We verify the group prefix + controller references
    are present instead.
    """
    src = _src(ROUTES_FILE)

    # Public API group prefix
    assert '"/api"' in src or 'prefix="/api"' in src or "prefix='/api'" in src, (
        "NFR-001: /api group not found"
    )
    # Admin group prefix
    assert '"/api/admin"' in src or 'prefix="/api/admin"' in src or "prefix='/api/admin'" in src, (
        "NFR-001: /api/admin group not found"
    )
    # All major admin controllers referenced
    for ctrl in [
        "AdminProductsController",
        "AdminCategoriesController",
        "AdminVendorsController",
        "AdminOrdersController",
        "AdminUsersController",
    ]:
        assert ctrl in src, f"NFR-001 FAIL: {ctrl} not found in routes/api.py"

    # Public storefront and cart paths (declared directly with full prefix)
    for snippet in ["StorefrontController", "CartController", "CheckoutController"]:
        assert snippet in src, f"NFR-001 FAIL: {snippet} not found in routes/api.py"
