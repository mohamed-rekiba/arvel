"""Media service helpers for the e-commerce kit."""

from __future__ import annotations

from typing import Any

from arvel.http import UploadFile
from arvel_image import Media
from arvel_image.media.exceptions import MediaError

from app.models.product import IMAGES_COLLECTION, Product


class MockMediaFile:
    """Minimal file-like object for unit-test attach_media() calls."""

    def __init__(self, content: bytes, filename: str) -> None:
        self.content = content
        self.filename = filename


async def attach_product_image(product: Product, file: UploadFile) -> dict[str, Any]:
    contents = await file.read()
    filename = file.filename or "upload"
    media = await product.add_media(contents, file_name=filename).to_media_collection(
        IMAGES_COLLECTION
    )
    return await serialize_media(media)


async def list_product_images(product: Product) -> list[dict[str, Any]]:
    rows = await product.get_media(IMAGES_COLLECTION)
    return [await serialize_media(media) for media in rows]


async def delete_product_image(product: Product, media_id: str) -> bool:
    rows = await product.get_media(IMAGES_COLLECTION)
    for media in rows:
        if str(media.id) == media_id or str(media.uuid) == media_id:
            await media.delete()
            return True
    return False


_CONVERSIONS: tuple[str, ...] = ("thumbnail", "card", "full")


async def serialize_media(media: Media) -> dict[str, Any]:
    seeded_url = media.get_custom_property("image_url")
    has_conversion = any(media.has_generated_conversion(name) for name in _CONVERSIONS)
    if seeded_url and not has_conversion:
        # Seeded sample media has no file on disk; the image lives at this URL.
        url = str(seeded_url)
        conversions = dict.fromkeys(_CONVERSIONS, url)
    else:
        url = await media.get_url()
        conversions = await _conversion_urls(media)
    return {
        "id": str(media.id),
        "uuid": media.uuid,
        "collection_name": media.collection_name,
        "filename": media.file_name,
        "mime_type": media.mime_type,
        "size": media.size,
        "url": url,
        "conversions": conversions,
        "metadata": {
            "custom_properties": media.custom_properties or {},
            "generated_conversions": media.generated_conversions or {},
            "responsive_images": media.responsive_images or {},
        },
    }


async def _conversion_urls(media: Media) -> dict[str, str]:
    urls: dict[str, str] = {}
    for name in _CONVERSIONS:
        urls[name] = await media.get_url(name) if media.has_generated_conversion(name) else ""
    return urls


__all__ = [
    "MediaError",
    "MockMediaFile",
    "attach_product_image",
    "delete_product_image",
    "list_product_images",
    "serialize_media",
]
