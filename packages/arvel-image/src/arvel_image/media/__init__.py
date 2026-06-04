"""arvel-image media-library runtime.

Public surface organized as a feature-per-file subpackage:

- :class:`Media` — the polymorphic ORM row (`media` table).
- :class:`HasMedia` — mixin that gives any host model the ``media``
  MorphMany plus ``add_image`` / ``get_media`` / ``clear_images``.
- :class:`MediaCollection` — declarative bucket; can be ``single_file``
  and carry a list of :class:`Conversion` instances.
- :class:`Conversion` — declarative chain of :class:`arvel_image.Image`
  ops plus a mime-type filter (``accepts``).
- :class:`PathGenerator` / :class:`DefaultPathGenerator` — pluggable
  scheme for original and conversion paths on disk.
- :class:`ConversionRunner` — synchronous executor; offloads Pillow
  work to a worker thread so it never blocks the event loop.
- :class:`FileAdder` — builder returned by :meth:`HasMedia.image_builder`.
"""

from __future__ import annotations

from arvel_image.media.collection import MediaCollection
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
from arvel_image.media.presets import CollectionConfig, ConversionConfig
from arvel_image.media.trait import HasMedia

# Intentionally not re-exported here either — reach the originals via their
# submodule paths, which stay stable:
#   * FileInfo                       → arvel_image.media.collection
#   * get_collection_preset          → arvel_image.media.presets
#   * register_collection_preset     → arvel_image.media.presets
#   * responsive-image helpers       → arvel_image.media.responsive_image_generator

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
    "InvalidMimeTypeError",
    "Media",
    "MediaCollection",
    "MediaError",
    "MediaLibrary",
    "PathGenerator",
    "QueuedConversionJob",
    "UnknownCollectionError",
    "get_conversion_runner",
    "get_path_generator",
    "set_conversion_runner",
    "set_path_generator",
]
