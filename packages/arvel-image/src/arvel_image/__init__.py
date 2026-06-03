"""arvel-image — image manipulation + media-library parity for Arvel.

Combines two Spatie packages:

- **spatie/image v3** — :class:`Image`, a fluent Pillow wrapper for
  resize / crop / fit / format / quality / optimize. Standalone, sync, no
  shelling out.
- **spatie/laravel-medialibrary v11** — a polymorphic ``media`` table
  plus a runtime layer (``Media``, ``HasMedia``, collections, conversions,
  file ingestion). Exposed through :class:`ImageServiceProvider`, which
  registers the migration as publishable under the ``arvel-image`` tag.
  The path generator and conversion runner resolve through
  ``get_path_generator`` / ``get_conversion_runner``; override them with
  ``set_path_generator`` / ``set_conversion_runner``.

Apps that only need ``Image`` can use it directly without booting an
Arvel application. Apps that want the media table run::

    arvel vendor:publish --tag=arvel-image
    arvel migrate

Then add :class:`HasMedia` to a model::

    class User(Model, HasMedia, Timestamps):
        __tablename__ = "users"
        ...

        def register_media_collections(self) -> None:
            (
                MediaCollection("avatar", single_file=True)
                .with_conversions(Conversion("thumb").fit("cover", 64, 64))
                .register_on(self)
            )

    media = await user.add_media(bytes_, file_name="avatar.jpg") \\
        .to_media_collection("avatar")
"""

from __future__ import annotations

from arvel_image.image import Image, UnsupportedFormatError
from arvel_image.media import (
    Conversion,
    ConversionFailedError,
    ConversionRunner,
    DefaultPathGenerator,
    FileAdder,
    FileInfo,
    FileTooLargeError,
    HasMedia,
    InvalidMimeTypeError,
    Media,
    MediaCollection,
    MediaError,
    MediaLibrary,
    PathGenerator,
    UnknownCollectionError,
    calculate_responsive_widths,
    generate_placeholder_svg,
    generate_responsive_images_for_media,
    get_conversion_runner,
    get_path_generator,
    set_conversion_runner,
    set_path_generator,
)
from arvel_image.media.jobs import QueuedConversionJob
from arvel_image.provider import ImageServiceProvider

# Ergonomic alias — HasMediaMixin and HasMedia are the same class.
HasMediaMixin = HasMedia

__all__ = [
    "Conversion",
    "ConversionFailedError",
    "ConversionRunner",
    "DefaultPathGenerator",
    "FileAdder",
    "FileInfo",
    "FileTooLargeError",
    "HasMedia",
    "HasMediaMixin",
    "Image",
    "ImageServiceProvider",
    "InvalidMimeTypeError",
    "Media",
    "MediaCollection",
    "MediaError",
    "MediaLibrary",
    "PathGenerator",
    "QueuedConversionJob",
    "UnknownCollectionError",
    "UnsupportedFormatError",
    "calculate_responsive_widths",
    "generate_placeholder_svg",
    "generate_responsive_images_for_media",
    "get_conversion_runner",
    "get_path_generator",
    "set_conversion_runner",
    "set_path_generator",
]
