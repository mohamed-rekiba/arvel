"""Shared controller dependencies: auth guards, service singletons, common middleware."""

from __future__ import annotations

__all__ = [
    "DB_TX",
    "carts",
    "categories",
    "orders",
    "products",
    "require_auth",
    "require_permission",
    "require_role_level",
    "role_level",
    "users",
    "vendors",
]

from app.models.user import User
from app.services.cart_service import CartService
from app.services.category_service import CategoryService
from app.services.order_service import OrderService
from app.services.product_service import ProductService
from app.services.user_service import UserService
from app.services.vendor_service import VendorService
from arvel.auth.guards import make_permission_guard, make_role_level_guard, require_auth
from arvel.http.exceptions import NotFoundException
from arvel.http.middleware.database_transaction import DatabaseTransaction
from arvel_permission.models import Role

DB_TX = [DatabaseTransaction()]

# ─── Auth guards wired to the kit's User model ────────────────────────────────

require_permission = make_permission_guard(User)
require_role_level = make_role_level_guard(User)


async def role_level(role_name: str) -> int:
    role = await Role.where(Role.name == role_name, Role.guard_name == "api").first()
    if role is None:
        raise NotFoundException(f"Role '{role_name}' not found.")
    return role.level


# ─── Service singletons ───────────────────────────────────────────────────────

products = ProductService()
carts = CartService()
orders = OrderService()
users = UserService()
categories = CategoryService()
vendors = VendorService()
