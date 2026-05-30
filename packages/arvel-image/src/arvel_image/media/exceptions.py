"""Exception hierarchy for the media-library runtime."""

from __future__ import annotations


class MediaError(Exception):
    """Base class for every error raised by ``arvel_image.media``."""


class ConversionFailedError(MediaError):
    """A :class:`~arvel_image.media.Conversion` raised while running.

    The original exception is chained as ``__cause__``.
    """


class UnknownCollectionError(MediaError):
    """Raised when a media collection is referenced but never registered."""


class InvalidMimeTypeError(MediaError):
    """File MIME type is not in the collection's accept list."""


class FileTooLargeError(MediaError):
    """File exceeds the collection's max_file_size limit."""


__all__ = [
    "ConversionFailedError",
    "FileTooLargeError",
    "InvalidMimeTypeError",
    "MediaError",
    "UnknownCollectionError",
]
