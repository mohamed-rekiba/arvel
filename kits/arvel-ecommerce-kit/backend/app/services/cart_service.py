"""CartService — cart CRUD with upsert-on-duplicate semantics."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from arvel.http.exceptions import NotFoundException, ValidationException
from arvel.logging.facade import Log

from app.models.cart import Cart
from app.models.cart_item import CartItem
from app.models.product import Product
from app.models.product_catalog import ProductCatalog
from app.services.product_service import ProductService


class CartService:
    def __init__(self) -> None:
        self._products = ProductService()

    async def get_or_create_cart(self, user_id: int) -> uuid.UUID:
        cart: Cart | None = await Cart.where(user_id=user_id).first()
        if cart is not None:
            return cart.id
        created: Cart | None = await Cart.create(user_id=user_id)
        if created is None:
            raise RuntimeError("Cart creation failed.")
        return created.id

    async def lock_cart(self, user_id: int) -> uuid.UUID:
        """Lock the user's cart row FOR UPDATE so concurrent checkouts serialize.

        Must run inside a transaction. A second checkout blocks here until the
        first commits; it then re-reads an emptied cart and fails as EmptyCart.
        """
        cart_id = await self.get_or_create_cart(user_id)
        await Cart.where(Cart.id == cart_id).lock_for_update().first()
        return cart_id

    async def get_cart(self, user_id: int, *, locale: str = "en") -> dict[str, Any]:
        cart_id = await self.get_or_create_cart(user_id)
        # with_("product.media") eager-loads each line's catalog row and its media —
        # belongs-to then morphMany — so _format_item touches the DB zero more times.
        items: list[CartItem] = (
            await CartItem.where(cart_id=cart_id)
            .with_("product.media")
            .order_by("created_at")
            .all()
        )
        formatted = [await self._format_item(i, locale) for i in items]
        total = float(
            sum(Decimal(str(i.unit_price_snapshot or 0)) * int(i.quantity) for i in items)
        )
        return {"id": str(cart_id), "items": formatted, "total": total}

    async def add_item(
        self, user_id: int, product_id: str, quantity: int, *, locale: str = "en"
    ) -> dict[str, Any]:
        Log.debug("cart.item.adding", product_id=product_id, quantity=quantity)
        cart_id = await self.get_or_create_cart(user_id)
        try:
            pid = uuid.UUID(product_id)
        except ValueError:
            raise NotFoundException(f"Product '{product_id}' not found.") from None

        existing: CartItem | None = await CartItem.where(cart_id=cart_id, product_id=pid).first()
        requested_quantity = quantity + int(existing.quantity) if existing is not None else quantity
        product: ProductCatalog | None = (
            await ProductCatalog.visible().where(ProductCatalog.id == pid).first()
        )
        if product is None:
            raise NotFoundException(f"Product '{product_id}' not found.")
        # The catalog view lags behind writes, so its stock_qty can green-light an
        # oversell that checkout later rejects. Check the authoritative product row
        # FOR UPDATE — same lock checkout uses — so the cart guard sees committed stock.
        stock = await self._locked_stock(pid)
        if stock < requested_quantity:
            raise ValidationException("Insufficient stock for cart item.")
        price = Decimal(str(product.price or 0))

        if existing is not None:
            existing.quantity += quantity
            # Re-snapshot to the current price so added units aren't billed at a
            # stale price from the first add. The whole line moves to today's price.
            existing.unit_price_snapshot = price
            await existing.save()
        else:
            await CartItem.create(
                cart_id=cart_id,
                product_id=pid,
                quantity=quantity,
                unit_price_snapshot=price,
            )
        Log.debug("cart.item.added", product_id=product_id)
        return await self.get_cart(user_id, locale=locale)

    async def update_item(
        self, user_id: int, item_id: str, quantity: int, *, locale: str = "en"
    ) -> dict[str, Any]:
        Log.debug("cart.item.updating", item_id=item_id, quantity=quantity)
        cart_id = await self.get_or_create_cart(user_id)
        item = await self._owned_item(cart_id, item_id)
        product: ProductCatalog | None = await item.product().first()
        if product is None:
            raise NotFoundException(f"Product '{item.product_id}' not found.")
        # Authoritative, FOR UPDATE — not the lagging catalog view (see add_item).
        if await self._locked_stock(item.product_id) < quantity:
            raise ValidationException("Insufficient stock for cart item.")
        item.quantity = quantity
        # Re-snapshot like add_item: any quantity change re-prices the whole line
        # to today's price, so a PATCH can't lock in a stale snapshot for checkout.
        item.unit_price_snapshot = Decimal(str(product.price or 0))
        await item.save()
        Log.debug("cart.item.updated", item_id=item_id, quantity=quantity)
        return await self.get_cart(user_id, locale=locale)

    async def remove_item(
        self, user_id: int, item_id: str, *, locale: str = "en"
    ) -> dict[str, Any]:
        cart_id = await self.get_or_create_cart(user_id)
        item = await self._owned_item(cart_id, item_id)
        await item.delete()
        Log.debug("cart.item.removed", item_id=item_id)
        return await self.get_cart(user_id, locale=locale)

    async def _locked_stock(self, product_id: uuid.UUID) -> int:
        """Committed stock from the product row, FOR UPDATE. Needs the request txn.

        Concurrent adds for the same product serialize here, so each reads the
        other's committed effect instead of a stale materialized-view snapshot.
        """
        product: Product | None = (
            await Product.where(Product.id == product_id).lock_for_update().first()
        )
        if product is None:
            raise NotFoundException(f"Product '{product_id}' not found.")
        return int(product.stock_qty)

    async def _owned_item(self, cart_id: uuid.UUID, item_id: str) -> CartItem:
        """Return the caller's cart line or 404. A bad/foreign id is not a silent no-op."""
        try:
            iid = int(item_id)
        except ValueError:
            raise NotFoundException("Cart item not found.") from None
        item: CartItem | None = await CartItem.where(
            CartItem.id == iid, CartItem.cart_id == cart_id
        ).first()
        if item is None:
            raise NotFoundException("Cart item not found.")
        return item

    async def get_cart_for_checkout(self, user_id: int) -> dict[str, Any]:
        """Returns flat checkout-ready cart data using price snapshots."""
        cart_id = await self.get_or_create_cart(user_id)
        items: list[CartItem] = await self._get_items(cart_id)
        # Decimal end-to-end: order.total must equal the sum of order_items.subtotal,
        # so the per-line price and the total derive from the same Decimal — no float
        # round-trip drift between the persisted total and its lines.
        checkout_items = [
            {
                "product_id": str(i.product_id),
                "quantity": int(i.quantity),
                "unit_price": Decimal(str(i.unit_price_snapshot)),
            }
            for i in items
        ]
        total = sum(Decimal(str(i.unit_price_snapshot)) * int(i.quantity) for i in items)
        return {"items": checkout_items, "total": total}

    async def clear_cart(self, user_id: int) -> None:
        cart_id = await self.get_or_create_cart(user_id)
        items: list[CartItem] = await CartItem.where(cart_id=cart_id).all()
        for item in items:
            await item.delete()
        Log.debug("cart.cleared", items=len(items))

    async def _get_items(self, cart_id: uuid.UUID) -> list[CartItem]:
        return await CartItem.where(cart_id=cart_id).order_by("created_at").all()

    async def _format_item(self, item: CartItem, locale: str) -> dict[str, Any]:
        # Served from the with_("product.media") eager cache — no query here.
        product = await item.product().first()
        # The catalog view keeps unpublished/soft-deleted rows (real_status != visible),
        # so presence alone isn't availability — checkout rejects anything not visible.
        available = product is not None and getattr(product, "real_status", None) == "visible"
        if product is not None:
            product_data = self._products.product_to_storefront(product, locale)
        else:
            # Product was unpublished or deleted after being added to the cart.
            product_data = {
                "id": str(item.product_id),
                "name": "",
                "slug": "",
                "short_description": "",
                "price": float(item.unit_price_snapshot),
                "stock": 0,
                "original_price": None,
                "thumbnail_url": None,
                "image_srcset": "",
                "image_sizes": "",
                "images": [],
                "rating": None,
                "rating_count": None,
                "is_new": False,
                "is_bestseller": False,
                "category_id": "",
                "category_name": "",
                "category_slug": "",
                "vendor_id": "",
                "vendor_name": "",
                "vendor_slug": "",
            }
        unit_price = float(item.unit_price_snapshot or 0)
        return {
            "id": str(item.id),
            "product_id": str(item.product_id),
            "quantity": int(item.quantity),
            "unit_price": unit_price,
            "subtotal": item.subtotal,
            "available": available,
            "product": product_data,
        }


__all__ = ["CartService"]
