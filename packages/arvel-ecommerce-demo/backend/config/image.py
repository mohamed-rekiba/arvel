"""arvel-image configuration — media collections and conversion presets.

The demo generates three conversions on every image upload:

- ``thumbnail``: 150x150 square crop, used in admin lists.
- ``card`` : 400x300 cover crop, used on storefront cards.
- ``full`` : 1200x900 contain fit, used on item show pages.

`arvel-image` runs conversions synchronously with thread-pool offload, so the
local demo does not need a queue worker for uploads.
"""

from __future__ import annotations

from arvel.support.env import env

default_disk: str = env("STORAGE_DEFAULT", "local")

collections: dict[str, dict[str, object]] = {
    "images": {
        "disk": default_disk,
        "max_size_bytes": 10 * 1024 * 1024,  # 10 MiB
        "max_files_per_subject": 4,
        "allowed_mimetypes": ["image/jpeg", "image/png", "image/webp", "image/gif"],
    },
}

conversions: dict[str, dict[str, dict[str, object]]] = {
    "images": {
        "thumbnail": {"width": 150, "height": 150, "fit": "cover", "quality": 85},
        "card": {"width": 400, "height": 300, "fit": "cover", "quality": 85},
        "full": {"width": 1200, "height": 900, "fit": "contain", "quality": 90},
    },
}
