"""ImageServiceProvider — wires arvel-image into an Arvel application.

``boot()`` does two things:

1. Registers ``create_media_table`` as a publishable migration so consumers
   can stamp it into ``database/migrations/`` with
   ``arvel vendor:publish --tag=arvel-image``.

2. If the application ships a ``config/image.py`` module with a ``collections``
   dict, it reads that config and registers the corresponding
   :class:`~arvel_image.MediaCollection` presets automatically — no separate
   provider or explicit wiring needed in the app.

The path generator and conversion runner resolve through module-level
accessors (``get_path_generator`` / ``get_conversion_runner``).  Defaults are
lazy, so there's nothing to bind here — an app overrides them by calling
``set_path_generator`` / ``set_conversion_runner`` from its own provider.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from arvel.providers.service_provider import ServiceProvider

from arvel_image.media.presets import CollectionConfig


class ImageServiceProvider(ServiceProvider):
    """Boot arvel-image inside an Arvel application."""

    async def boot(self) -> None:
        from arvel_image import migrations as image_migrations  # noqa: PLC0415

        stub = Path(image_migrations.__file__).parent / "create_media_table.py"
        self.publishes(
            {stub: "database/migrations"},
            tag="arvel-image",
            is_migrations=True,
        )

        self._register_collections_from_config()

    def _register_collections_from_config(self) -> None:
        import importlib  # noqa: PLC0415

        try:
            image_cfg = importlib.import_module("config.image")
        except ImportError:
            return

        raw = getattr(image_cfg, "collections", None)
        if not raw:
            return
        collections = cast("dict[str, CollectionConfig]", raw)

        from arvel_image.media.collection import MediaCollection  # noqa: PLC0415
        from arvel_image.media.conversion import Conversion  # noqa: PLC0415
        from arvel_image.media.presets import register_collection_preset  # noqa: PLC0415

        for coll_name, coll_cfg in collections.items():
            coll = MediaCollection(coll_name)

            if disk := coll_cfg.get("disk"):
                coll.use_disk(disk)
            if mimes := coll_cfg.get("allowed_mimetypes"):
                coll.accept_mime_types(list(mimes))
            if max_size := coll_cfg.get("max_size_bytes"):
                coll.max_file_size(max_size)
            if max_files := coll_cfg.get("max_files"):
                coll.only_keep_latest(max_files)

            for conv_name, conv_cfg in (coll_cfg.get("conversions") or {}).items():
                conv = (
                    Conversion(conv_name)
                    .fit(conv_cfg.get("fit", "contain"), conv_cfg["width"], conv_cfg["height"])
                    .quality(conv_cfg.get("quality", 85))
                )
                if conv_cfg.get("responsive"):
                    conv.generate_responsive_images()
                coll.with_conversions(conv)

            register_collection_preset(coll_name, coll)
