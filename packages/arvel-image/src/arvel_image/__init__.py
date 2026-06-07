"""arvel-image — image manipulation + polymorphic media for Arvel.

Two pieces:

- :class:`Image` — fluent Pillow wrapper for resize / crop / fit / format /
  quality / optimize. Standalone, sync, no subprocess.
- The media subsystem (:class:`Media`, :class:`HasMedia`) — a polymorphic
  ``media`` table plus the runtime to ingest files, run conversions, build
  responsive variants, and serialize everything for an API.

Apps that only need ``Image`` can use it directly. Apps that want the
media table run::

    arvel vendor:publish --tag=arvel-image
    arvel migrate

Then add :class:`HasMedia` to a model::

    class User(HasMedia, Model, Timestamps):
        __tablename__ = "users"
        __media_collection__ = "avatar"

    media = await user.add_image(bytes_, file_name="avatar.jpg")

``user.to_dict()`` automatically includes serialized media when the
``media`` relation is eager-loaded — no per-app serializers needed.
"""

from __future__ import annotations

from arvel_image.image import Image, UnsupportedFormatError, set_max_pixels
from arvel_image.media import (
    CollectionConfig,
    Conversion,
    ConversionConfig,
    ConversionFailedError,
    ConversionRunner,
    DefaultPathGenerator,
    FileAdder,
    FileTooLargeError,
    HasMedia,
    InvalidMimeTypeError,
    Media,
    MediaCollection,
    MediaError,
    MediaLibrary,
    PathGenerator,
    UnknownCollectionError,
    get_conversion_runner,
    get_path_generator,
    set_conversion_runner,
    set_path_generator,
)
from arvel_image.media.jobs import QueuedConversionJob
from arvel_image.provider import ImageServiceProvider

# Intentionally not re-exported at the package level — submodule paths stay
# stable for framework-internal callers and the rare advanced user:
#   * FileInfo                      → arvel_image.media.collection
#   * get_collection_preset         → arvel_image.media.presets
#   * register_collection_preset    → arvel_image.media.presets
#   * calculate_responsive_widths,
#     copy_responsive_images,
#     generate_placeholder_svg,
#     generate_responsive_images_for_media
#                                   → arvel_image.media.responsive_image_generator
# These were re-exported pre-1.0 only because early tests reached for them;
# none are user-facing API. Promoting them back is the breaking change, not
# moving them here.

__all__ = [
    "CollectionConfig",
    "Conversion",
    "ConversionConfig",
    "ConversionFailedError",
    "ConversionRunner",
    "DefaultPathGenerator",
    "FileAdder",
    "FileTooLargeError",
    "HasMedia",
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
    "get_conversion_runner",
    "get_path_generator",
    "set_conversion_runner",
    "set_max_pixels",
    "set_path_generator",
]
