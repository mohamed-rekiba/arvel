"""CartItem model — one line per product in the cart."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar

from arvel.database import Model, Timestamps, decimal, foreign_uuid, id_

if TYPE_CHECKING:
    from arvel.database.orm.relations import BelongsTo

    from app.models.cart import Cart
    from app.models.product_catalog import ProductCatalog


class CartItem(Model, Timestamps):
    __tablename__ = "cart_items"

    # Cart pruning keys off carts.updated_at (see Cart.prunable_query). Without this,
    # a cart whose lines change but whose row never updates looks abandoned and gets
    # reaped. Touching the parent on every line write keeps active carts alive.
    __touches__: ClassVar[tuple[str, ...]] = ("cart",)

    id: int = id_()
    cart_id: uuid.UUID = foreign_uuid("carts.id", on_delete="CASCADE")
    product_id: uuid.UUID = foreign_uuid("products.id", on_delete="CASCADE")
    quantity: int = 1
    unit_price_snapshot: Decimal = decimal(10, 2, default=Decimal(0))

    def cart(self) -> BelongsTo[Cart]:
        return self.belongs_to("Cart", foreign_key="cart_id")

    def product(self) -> BelongsTo[ProductCatalog]:
        # Points at the storefront read model (products_catalog.id == products.id),
        # so `.with_("product")` + get_media serve cart rows without per-item lookups.
        return self.belongs_to("ProductCatalog", foreign_key="product_id")


__all__ = ["CartItem"]
