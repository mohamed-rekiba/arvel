"""arvel-image configuration — media collections and conversion presets.

``ImageServiceProvider.boot`` reads ``collections`` and builds the
``MediaCollection`` presets that models reference via ``__media_collection__``.

Each entry is a :class:`~arvel_image.CollectionConfig` with conversions
nested inline — one dict is the single source of truth for a collection.
"""

from __future__ import annotations

from arvel_image import CollectionConfig

import config.filesystems as fs_cfg

default: str = "images"

collections: dict[str, CollectionConfig] = {
    default: {
        "disk": fs_cfg.default,
        "max_size_bytes": 5 * 1024 * 1024,  # 5 MiB
        "max_files": 4,
        "allowed_mimetypes": ["image/jpeg", "image/png", "image/webp", "image/gif"],
        "conversions": {
            "thumbnail": {"width": 150, "height": 150, "fit": "cover", "quality": 85},
            "card": {
                "width": 400,
                "height": 300,
                "fit": "cover",
                "quality": 85,
                "responsive": True,
            },
            "full": {
                "width": 1200,
                "height": 900,
                "fit": "contain",
                "quality": 90,
                "responsive": True,
            },
        },
    },
}
