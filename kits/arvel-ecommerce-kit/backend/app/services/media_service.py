"""Media service helpers for the e-commerce kit.

Thin wrapper around ``Product.add_image()`` and the eager media relation.
The default collection comes from ``Product.__media_collection__``, so callers
never name it.
"""

from __future__ import annotations

from typing import Any

from arvel_image.media.exceptions import MediaError

from app.models.product import Product


async def attach_product_image(product: Product, contents: bytes, filename: str) -> dict[str, Any]:
    # contents is read with a hard cap in the controller — never read the raw
    # UploadFile here, or an oversized body lands in worker memory.
    media = await product.add_image(contents, file_name=filename)
    return media.to_dict()


def list_product_images(product: Product) -> list[dict[str, Any]]:
    return [m.to_dict() for m in product.get_media()]


async def delete_product_image(product: Product, media_id: str) -> bool:
    for media in product.get_media():
        if str(media.id) == media_id or str(media.uuid) == media_id:
            await media.delete()
            return True
    return False


__all__ = [
    "MediaError",
    "attach_product_image",
    "delete_product_image",
    "list_product_images",
]
