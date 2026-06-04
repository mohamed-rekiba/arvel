"""Named MediaCollection preset registry + configuration type contracts.

Two pieces:

1. **Config TypedDicts** (``CollectionConfig``, ``ConversionConfig``) — the schema
   you fill in inside ``config/image.py``. Importing them keeps the config typed
   end-to-end.

2. **Preset registry** (``register_collection_preset`` / ``get_collection_preset``)
   — a module-level accessor pair, same pattern as ``set_path_generator`` /
   ``set_conversion_runner``. The provider reads ``config.image.collections`` at
   boot, translates each entry to a ``MediaCollection``, and registers it under
   the same name. Any host whose ``__media_collection__`` matches a registered
   preset auto-binds to it via :meth:`HasMedia.register_media_collections`.

Typical wiring::

    # config/image.py (kit)
    from arvel_image import CollectionConfig

    collections: dict[str, CollectionConfig] = {
        "images": {
            "disk": "public",
            "conversions": {
                "thumbnail": {"width": 150, "height": 150, "fit": "cover", "quality": 85},
                "card": {
                    "width": 400, "height": 300, "fit": "cover",
                    "quality": 85, "responsive": True,
                },
            },
        },
    }

    # app/models/product.py (kit)
    from arvel_image import HasMedia

    class Product(HasMedia, Model, Timestamps):
        __media_collection__ = "images"
        # HasMedia.register_media_collections auto-binds via the preset.

For programmatic registration (without ``config/image.py``), call
``register_collection_preset(name, MediaCollection(...))`` from your own provider.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Required, TypedDict

if TYPE_CHECKING:
    from arvel_image.media.collection import MediaCollection

# ── config schema ──────────────────────────────────────────────────────────


class ConversionConfig(TypedDict, total=False):
    """Per-conversion parameters used in ``config/image.py``."""

    width: Required[int]
    height: Required[int]
    fit: str  # default "contain"
    quality: int  # default 85
    responsive: bool  # default False


class CollectionConfig(TypedDict, total=False):
    """Per-collection parameters used in ``config/image.py``.

    ``conversions`` is a nested dict of conversion name → :class:`ConversionConfig`,
    keeping all collection settings in one place instead of a parallel top-level dict.
    """

    disk: str
    max_size_bytes: int
    max_files: int
    allowed_mimetypes: list[str]
    conversions: dict[str, ConversionConfig]


# ── preset registry ────────────────────────────────────────────────────────

_presets: dict[str, MediaCollection] = {}


def register_collection_preset(name: str, collection: MediaCollection) -> None:
    """Store a named MediaCollection so models can reference it by name."""
    _presets[name] = collection


def get_collection_preset(name: str) -> MediaCollection:
    """Return the preset, raising KeyError with a helpful message if not found."""
    try:
        return _presets[name]
    except KeyError:
        registered = sorted(_presets)
        msg = (
            f"No collection preset {name!r} registered. "
            f"Call register_collection_preset() in your service provider before using the model. "
            f"Registered presets: {registered or ['(none)']}"
        )
        raise KeyError(msg) from None


__all__ = [
    "CollectionConfig",
    "ConversionConfig",
    "get_collection_preset",
    "register_collection_preset",
]
