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


async def serialize_media(media: Media) -> dict[str, Any]:
    url = await media.get_url()
    conversions = await _conversion_urls(media)

    ri = media.responsive_images or {}
    srcset = await media.get_srcset() if "medialibrary_original" in ri else ""
    placeholder_svg = media.get_placeholder_svg() if "medialibrary_original" in ri else ""
    conversion_srcsets = await _conversion_srcsets(media, ri)

    return {
        "id": str(media.id),
        "uuid": media.uuid,
        "collection_name": media.collection_name,
        "filename": media.file_name,
        "mime_type": media.mime_type,
        "size": media.size,
        "url": url,
        "srcset": srcset,
        "placeholder_svg": placeholder_svg,
        "conversions": conversions,
        "conversion_srcsets": conversion_srcsets,
        "metadata": {
            "custom_properties": media.custom_properties or {},
            "generated_conversions": media.generated_conversions or {},
        },
    }


async def _conversion_urls(media: Media) -> dict[str, str]:
    generated: dict[str, Any] = media.generated_conversions or {}
    return {
        name: await media.get_url(name) if generated.get(name) else ""
        for name in generated
    }


async def _conversion_srcsets(media: Media, ri: dict[str, Any]) -> dict[str, str]:
    # Iterate whatever responsive_images actually contains — no hard-coded list.
    # "medialibrary_original" is the collection-level key, not a conversion name.
    result: dict[str, str] = {}
    for name in ri:
        if name != "medialibrary_original" and media.has_generated_conversion(name):
            result[name] = await media.get_srcset(name)
    return result


__all__ = [
    "MediaError",
    "MockMediaFile",
    "attach_product_image",
    "delete_product_image",
    "list_product_images",
    "serialize_media",
]
