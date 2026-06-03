"""ImageServiceProvider — wires arvel-image into an Arvel app.

``boot()`` registers ``create_media_table`` as a publishable migration so
consumers can stamp it into ``database/migrations/`` with
``arvel vendor:publish --tag=arvel-image``.

The path generator and conversion runner resolve through module-level
accessors (``get_path_generator`` / ``get_conversion_runner``), the same
app-scoped accessor pattern Arvel uses for ``AuthService``. Defaults are
lazy, so there's nothing to bind here — an app overrides them by calling
``set_path_generator`` / ``set_conversion_runner`` from its own provider.

The image-manipulation API (:class:`arvel_image.Image`) is standalone —
apps that only transform bytes don't need the provider at all.
"""

from __future__ import annotations

from pathlib import Path

from arvel.providers.service_provider import ServiceProvider


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
