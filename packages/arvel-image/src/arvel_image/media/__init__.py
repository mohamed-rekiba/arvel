"""arvel-image media-library runtime — Spatie ``laravel-medialibrary`` v11 parity.

Public surface organized as a feature-per-file subpackage:

- :class:`Media` — the polymorphic ORM row (`media` table).
- :class:`HasMedia` — mixin that gives any host model the
  ``media`` MorphMany plus the ``add_media`` / ``get_media`` /
  ``clear_media_collection`` API.
- :class:`MediaCollection` — declarative bucket; can be ``single_file``
  and carry a list of :class:`Conversion` instances.
- :class:`Conversion` — declarative chain of :class:`arvel_image.Image`
  ops plus a mime-type filter (``accepts``).
- :class:`PathGenerator` / :class:`DefaultPathGenerator` — pluggable
  scheme for original and conversion paths on disk.
- :class:`ConversionRunner` — synchronous executor; offloads Pillow
  work to a worker thread so it never blocks the event loop.
- :class:`FileAdder` — builder returned by :meth:`HasMedia.add_media`.

See package architecture docs for runtime-layer decisions
(synchronous conversions, short class-name polymorphic discriminator,
default path scheme matching Spatie verbatim).
"""

from __future__ import annotations

from arvel_image.media.collection import FileInfo, MediaCollection
from arvel_image.media.conversion import Conversion
from arvel_image.media.conversion_runner import (
    ConversionRunner,
    get_conversion_runner,
    set_conversion_runner,
)
from arvel_image.media.exceptions import (
    ConversionFailedError,
    FileTooLargeError,
    InvalidMimeTypeError,
    MediaError,
    UnknownCollectionError,
)
from arvel_image.media.file_adder import FileAdder
from arvel_image.media.jobs import QueuedConversionJob
from arvel_image.media.media_library import MediaLibrary
from arvel_image.media.model import Media
from arvel_image.media.path_generator import (
    DefaultPathGenerator,
    PathGenerator,
    get_path_generator,
    set_path_generator,
)
from arvel_image.media.responsive_image_generator import (
    calculate_responsive_widths,
    generate_placeholder_svg,
    generate_responsive_images_for_media,
)
from arvel_image.media.trait import HasMedia

__all__ = [
    "Conversion",
    "ConversionFailedError",
    "ConversionRunner",
    "DefaultPathGenerator",
    "FileAdder",
    "FileInfo",
    "FileTooLargeError",
    "HasMedia",
    "InvalidMimeTypeError",
    "Media",
    "MediaCollection",
    "MediaError",
    "MediaLibrary",
    "PathGenerator",
    "QueuedConversionJob",
    "UnknownCollectionError",
    "calculate_responsive_widths",
    "generate_placeholder_svg",
    "generate_responsive_images_for_media",
    "get_conversion_runner",
    "get_path_generator",
    "set_conversion_runner",
    "set_path_generator",
]
