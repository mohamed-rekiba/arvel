"""Storefront category API and cart visibility guard contracts."""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arvel.http.exceptions import NotFoundException, ValidationException

BASE_DIR = Path(__file__).parents[2]
API_ROUTES = BASE_DIR / "routes" / "api.py"
CART_SERVICE = BASE_DIR / "app" / "services" / "cart_service.py"
CART_SCHEMAS = BASE_DIR / "app" / "http" / "controllers" / "_schemas.py"
PRODUCT_SERVICE = BASE_DIR / "app" / "services" / "product_service.py"
ORDER_SERVICE = BASE_DIR / "app" / "services" / "order_service.py"
CHECKOUT_CTRL = BASE_DIR / "app" / "http" / "controllers" / "checkout.py"
STOREFRONT_CTRL = BASE_DIR / "app" / "http" / "controllers" / "storefront.py"


def _src(path: Path) -> str:
    return path.read_text()


def test_storefront_category_route_binds_to_controller() -> None:
    # routes/api.py is routing-only: the category detail route delegates to the
    # storefront controller instead of inlining a handler.
    routes = _src(API_ROUTES)

    assert '"/categories/{slug}"' in routes
    assert "controller=StorefrontController" in routes
    assert 'action="products_catalog"' in routes


def test_storefront_category_controller_uses_published_products_service() -> None:
    controller = _src(STOREFRONT_CTRL)

    assert "list_published_by_category_slug(" in controller
    assert (
        'resolved_locale = locale or getattr(request.state, "locale", "en") or "en"' in controller
    )


def test_category_listing_filters_the_published_products_view_by_category_slug() -> None:
    service = _src(PRODUCT_SERVICE)

    assert "def list_published_by_category_slug(" in service
    assert 'where_json_path("category_slug", locale, category_slug)' in service
    assert 'keyset=["published_at DESC", "id ASC"]' in service


def test_cart_add_item_never_reads_raw_products_table() -> None:
    service = _src(CART_SERVICE)

    assert "from app.models.product import Product" not in service
    assert "from app.models.product_catalog import ProductCatalog" in service
    assert "ProductCatalog.where(" in service


def test_checkout_validates_catalog_product_before_stock_lock() -> None:
    service = _src(ORDER_SERVICE)
    checkout_start = service.index("    async def checkout(")
    list_orders_start = service.index("\n    async def list_orders", checkout_start)
    checkout_source = service[checkout_start:list_orders_start]

    assert "from app.models.product_catalog import ProductCatalog" in service
    assert "ProductCatalog.where(" in checkout_source
    assert checkout_source.index("ProductCatalog.where(") < checkout_source.index("Product.where(")
    assert "name_data = published.name or {}" in checkout_source


def test_checkout_endpoint_uses_observer_refresh() -> None:
    # Refresh is handled by ProductsCatalogRefreshObserver after model commits,
    # not by background_tasks in the route — verify no raw SQL in checkout.
    checkout = _src(CHECKOUT_CTRL)
    assert "REFRESH MATERIALIZED VIEW" not in checkout
    assert "ProductsCatalogRefreshObserver" not in checkout  # observer wired in provider


def test_cart_payloads_reject_non_positive_quantities() -> None:
    schemas = _src(CART_SCHEMAS)

    assert "quantity: Annotated[int, Field(ge=1)] = 1" in schemas
    assert "quantity: Annotated[int, Field(ge=1)]" in schemas


@pytest.mark.asyncio
async def test_cart_add_item_rejects_products_absent_from_catalog() -> None:
    from app.services.cart_service import CartService

    svc = CartService()
    product_id = "01960000-0000-7000-8000-000000000111"

    with (
        patch.object(svc, "get_or_create_cart", AsyncMock(return_value=uuid.uuid4())),
        patch("app.services.cart_service.CartItem") as cart_item,
        patch("app.services.cart_service.ProductCatalog") as product_catalog,
    ):
        cart_item.where.return_value = MagicMock(first=AsyncMock(return_value=None))
        product_catalog.id = object()
        product_catalog.where.return_value = MagicMock(first=AsyncMock(return_value=None))

        with pytest.raises(NotFoundException):
            await svc.add_item(1, product_id, 1)


@pytest.mark.asyncio
async def test_cart_add_item_uses_catalog_price_snapshot() -> None:
    from app.services.cart_service import CartService

    svc = CartService()
    cart_id = uuid.uuid4()
    product_id = "01960000-0000-7000-8000-000000000111"
    product = MagicMock()
    product.price = Decimal("19.99")
    product.stock_qty = 5

    with (
        patch.object(svc, "get_or_create_cart", AsyncMock(return_value=cart_id)),
        patch.object(svc, "get_cart", AsyncMock(return_value={"items": [], "total": 0})),
        patch("app.services.cart_service.ProductCatalog") as product_catalog,
        patch("app.services.cart_service.CartItem") as cart_item,
    ):
        product_catalog.id = object()
        product_catalog.where.return_value = MagicMock(first=AsyncMock(return_value=product))
        cart_item.where.return_value = MagicMock(first=AsyncMock(return_value=None))
        cart_item.create = AsyncMock()

        await svc.add_item(1, product_id, 2)

    cart_item.create.assert_awaited_once_with(
        cart_id=cart_id,
        product_id=uuid.UUID(product_id),
        quantity=2,
        unit_price_snapshot=Decimal("19.99"),
    )


@pytest.mark.asyncio
async def test_cart_add_item_rejects_quantity_above_catalog_stock() -> None:
    from app.services.cart_service import CartService

    svc = CartService()
    cart_id = uuid.uuid4()
    product_id = "01960000-0000-7000-8000-000000000111"
    product = MagicMock()
    product.stock_qty = 1

    with (
        patch.object(svc, "get_or_create_cart", AsyncMock(return_value=cart_id)),
        patch("app.services.cart_service.ProductCatalog") as product_catalog,
        patch("app.services.cart_service.CartItem") as cart_item,
    ):
        cart_item.where.return_value = MagicMock(first=AsyncMock(return_value=None))
        product_catalog.id = object()
        product_catalog.where.return_value = MagicMock(first=AsyncMock(return_value=product))

        with pytest.raises(ValidationException):
            await svc.add_item(1, product_id, 2)


@pytest.mark.asyncio
async def test_product_service_uses_get_media_for_images() -> None:
    """Storefront image loading uses product.get_media() not raw Media.query()."""
    from app.services.product_service import ProductService

    published = MagicMock()
    published.id = uuid.UUID("01960000-0000-7000-8000-000000000111")
    published.name = {"en": "Test"}
    published.slug = {"en": "test"}
    published.description = {"en": "Demo"}
    published.price = Decimal("19.99")
    published.stock_qty = 4
    published.category_id = None
    published.category_name = {}
    published.category_slug = {}
    published.category_parent_id = None
    published.parent_category_name = {}
    published.parent_category_slug = {}
    published.vendor_id = None
    published.vendor_name = ""
    published.vendor_slug = ""
    media = MagicMock()
    media.custom_properties = {}
    media.generated_conversions = {"thumbnail": True, "card": True, "full": True}
    media.get_url = AsyncMock(
        side_effect=[
            "/storage/media/thumb.jpg",
            "/storage/media/card.jpg",
            "/storage/media/full.jpg",
        ]
    )
    published.get_media = AsyncMock(return_value=[media])

    with patch("app.services.product_service.ProductCatalog") as product_catalog_cls:
        product_query = MagicMock()
        product_query.where.return_value = product_query
        product_query.where_json_path.return_value = MagicMock(
            first=AsyncMock(return_value=published)
        )
        product_catalog_cls.query.return_value = product_query
        product_catalog_cls.real_status = MagicMock()

        result = await ProductService().get_published_by_slug("test")

    assert result is not None
    assert result["thumbnail_url"] == "/storage/media/thumb.jpg"
    assert result["image_srcset"] == (
        "/storage/media/thumb.jpg 150w, /storage/media/card.jpg 400w, /storage/media/full.jpg 1200w"
    )
    assert result["image_sizes"]
    published.get_media.assert_awaited_once()
    media.get_url.assert_any_await("thumbnail")
    media.get_url.assert_any_await("card")
    media.get_url.assert_any_await("full")
