"""Pydantic response schemas for all API endpoints.

These give FastAPI enough type information to generate a useful OpenAPI spec,
so the generated frontend client has precise types instead of `{ [key]: unknown }`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Out(BaseModel):
    model_config = ConfigDict(frozen=True)


# ── Error envelope ────────────────────────────────────────────────────────────
# Every non-2xx response from this API uses this envelope.


class ErrorDetailOut(_Out):
    field: str
    issue: str


class ErrorBodyOut(_Out):
    code: str
    message: str
    details: list[ErrorDetailOut] | None = None


class ApiErrorOut(_Out):
    """Unified error envelope returned for 400/401/403/404/409/422/500."""

    error: ErrorBodyOut


# ── Shared ────────────────────────────────────────────────────────────────────


class PaginationMeta(_Out):
    next_cursor: str | None
    has_more: bool


# ── Auth ──────────────────────────────────────────────────────────────────────


class TokenOut(_Out):
    access_token: str
    expires_in: int


class MeOut(_Out):
    id: int
    name: str
    email: str
    locale: str
    theme: str
    roles: list[str]
    permissions: list[str]
    # Highest role level the caller holds. Lets the UI gate level-restricted
    # actions (e.g. force-delete needs 100) instead of showing a button that 403s.
    role_level: int


class RegisterOut(_Out):
    user_id: str


# ── Storefront ────────────────────────────────────────────────────────────────


class ProductCardOut(_Out):
    id: str
    name: str
    slug: str
    short_description: str | None
    price: float
    stock: int
    original_price: float | None
    thumbnail_url: str | None
    image_srcset: str
    image_sizes: str
    rating: float | None
    rating_count: int | None
    is_new: bool
    is_bestseller: bool
    category_id: str | None
    category_name: str | None
    category_slug: str | None
    category_parent_id: str | None
    parent_category_name: str | None
    parent_category_slug: str | None
    vendor_id: str | None
    vendor_name: str | None
    vendor_slug: str | None


class ProductListOut(_Out):
    data: list[ProductCardOut]
    pagination: PaginationMeta


class StorefrontProductImageOut(_Out):
    """Per-image payload — mirrors ``Media.to_dict()`` from arvel-image.

    The frontend reads URLs from the ``conversions`` and ``srcsets`` dicts
    keyed by conversion name (``thumbnail``, ``card``, ``full``, …) instead of
    hard-coded fields. ``url`` is the original.
    """

    id: str
    uuid: str | None = None
    collection_name: str
    name: str
    file_name: str
    mime_type: str | None = None
    size: int
    disk: str
    order: int | None = None
    custom_properties: dict[str, Any] = Field(default_factory=dict)
    url: str
    conversions: dict[str, str] = Field(default_factory=dict)
    srcsets: dict[str, str] = Field(default_factory=dict)
    placeholder_svg: str = ""
    created_at: str | None = None
    updated_at: str | None = None


class ProductDetailCardOut(ProductCardOut):
    """ProductCardOut extended with the full image gallery for the detail page."""

    images: list[StorefrontProductImageOut]


class ProductDetailOut(_Out):
    data: ProductDetailCardOut


class SearchOut(_Out):
    data: list[ProductCardOut]


# ── Cart ──────────────────────────────────────────────────────────────────────


class CartItemOut(_Out):
    id: str
    product_id: str
    quantity: int
    # Price locked in when the item was added — what checkout actually charges.
    # product.price is the live catalog price and may have since drifted.
    unit_price: float
    subtotal: float
    product: ProductCardOut


class CartOut(_Out):
    id: str
    items: list[CartItemOut]
    # Sum of line subtotals at snapshot prices; matches the charged amount.
    total: float


class CartWrapperOut(_Out):
    data: CartOut


# ── Account orders ────────────────────────────────────────────────────────────


class OrderItemOut(_Out):
    id: str
    product_id: str
    product_name: str
    quantity: int
    unit_price: float
    subtotal: float


class OrderOut(_Out):
    id: str
    user_id: int
    status: str
    total: float
    shipping_address: dict[str, Any]
    created_at: str
    items: list[OrderItemOut]


class OrderListOut(_Out):
    data: list[OrderOut]


class OrderWrapperOut(_Out):
    data: OrderOut


# ── Admin products ────────────────────────────────────────────────────────────


class AdminProductOut(_Out):
    id: str
    name: dict[str, str]
    slug: dict[str, str]
    description: dict[str, str]
    price: float
    stock_qty: int
    status: str
    real_status: str | None
    published_at: str | None
    category_id: str | None
    vendor_id: str | None
    created_at: str | None
    updated_at: str | None
    deleted_at: str | None


class AdminProductListOut(_Out):
    data: list[AdminProductOut]
    total: int


class AdminProductWrapperOut(_Out):
    data: AdminProductOut


class CatalogRefreshOut(_Out):
    refreshed_at: str
    product_count: int


class MediaOut(_Out):
    model_config = ConfigDict(frozen=True, extra="allow")
    id: str
    url: str


class MediaListOut(_Out):
    data: list[MediaOut]


class MediaWrapperOut(_Out):
    data: MediaOut


# ── Admin categories ──────────────────────────────────────────────────────────


class AdminCategoryOut(_Out):
    id: str
    name: dict[str, str]
    slug: dict[str, str]
    status: str
    published_at: str | None
    parent_id: str | None
    deleted_at: str | None


class AdminCategoryListOut(_Out):
    data: list[AdminCategoryOut]
    total: int


class AdminCategoryWrapperOut(_Out):
    data: AdminCategoryOut


class StorefrontCategoryListOut(_Out):
    data: list[AdminCategoryOut]


# ── Admin vendors ─────────────────────────────────────────────────────────────


class AdminVendorOut(_Out):
    id: str
    name: str
    slug: str
    description: str | None
    status: str
    published_at: str | None
    deleted_at: str | None


class AdminVendorListOut(_Out):
    data: list[AdminVendorOut]
    total: int


class AdminVendorWrapperOut(_Out):
    data: AdminVendorOut


# ── Admin orders ──────────────────────────────────────────────────────────────


class AdminOrderItemProductOut(_Out):
    name: dict[str, str]


class AdminOrderItemOut(_Out):
    id: str
    product_id: str
    product_name: str
    quantity: int
    unit_price: float
    subtotal: float
    product: AdminOrderItemProductOut | None = None


class AdminOrderUserOut(_Out):
    id: int
    name: str
    email: str


class AdminOrderOut(_Out):
    id: str
    user_id: int
    status: str
    total: float
    shipping_address: dict[str, Any]
    created_at: str
    items: list[AdminOrderItemOut]
    user: AdminOrderUserOut | None = None


class AdminOrderListOut(_Out):
    data: list[AdminOrderOut]
    total: int


class AdminOrderWrapperOut(_Out):
    data: AdminOrderOut


class BestSellerOut(_Out):
    product_id: str | None
    name: str
    revenue: float
    units_sold: int


class BestSellersListOut(_Out):
    data: list[BestSellerOut]


# ── Admin users ───────────────────────────────────────────────────────────────


class AdminUserOut(_Out):
    id: int
    name: str
    email: str
    roles: list[str]
    permissions: list[str]
    direct_permissions: list[str]
    suspended_at: str | None
    deleted_at: str | None


class AdminUserListOut(_Out):
    data: list[AdminUserOut]
    total: int


class AdminUserWrapperOut(_Out):
    data: AdminUserOut


# ── Admin roles / permissions ─────────────────────────────────────────────────


class RoleOut(_Out):
    id: int
    name: str
    guard_name: str
    level: int
    permissions: list[str] = Field(default_factory=list)


class PermissionOut(_Out):
    id: int
    name: str
    guard_name: str


class RolesListOut(_Out):
    data: list[RoleOut]


# ── Admin dashboard ───────────────────────────────────────────────────────────


class DashboardRevenuePointOut(_Out):
    date: str
    revenue: float


class DashboardStatsOut(_Out):
    total_revenue: float
    total_orders: int
    unique_customers: int
    avg_order_value: float
    status_counts: dict[str, int]
    revenue_last_7_days: list[DashboardRevenuePointOut]


class PermissionsListOut(_Out):
    data: list[PermissionOut]


# ── Admin translations ────────────────────────────────────────────────────────


class TranslationEntryOut(_Out):
    model: str
    id: str
    fields: dict[str, dict[str, str]]


class TranslationsListOut(_Out):
    data: list[TranslationEntryOut]
