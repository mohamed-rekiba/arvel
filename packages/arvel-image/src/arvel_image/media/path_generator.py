"""Path-generator protocol + default scheme.

Default scheme::

    {id}/{file_name}                                  # original
    {id}/conversions/{conversion}-{file_name}         # derived

``PathGenerator`` is a :class:`typing.Protocol`, so any class with the
matching shape can replace the binding without inheriting from a base.

Call :func:`set_path_generator` (e.g. in ``ImageServiceProvider.register``) to
swap in a custom implementation app-wide.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from arvel_image.media.model import Media

# Module-level override — None means "use DefaultPathGenerator"
_custom_path_generator: PathGenerator | None = None


@runtime_checkable
class PathGenerator(Protocol):
    """Resolve disk paths for media originals and their conversions."""

    def path_for(self, media: Media) -> str:
        """Disk path of the original file for ``media``."""
        ...

    def path_for_conversion(self, media: Media, conversion: str) -> str:
        """Disk path of ``media``'s ``conversion`` derivative."""
        ...


class DefaultPathGenerator:
    """Default layout. Stable across versions; safe for URLs."""

    def path_for(self, media: Media) -> str:
        return f"{media.id}/{media.file_name}"

    def path_for_conversion(self, media: Media, conversion: str) -> str:
        return f"{media.id}/conversions/{conversion}-{media.file_name}"


def set_path_generator(gen: PathGenerator) -> None:
    """Override the module-level path generator used by FileAdder and Media

    Call this in ``ImageServiceProvider.register()`` or app bootstrap.
    Pass ``DefaultPathGenerator()`` to reset to the default.
    """
    global _custom_path_generator  # noqa: PLW0603
    _custom_path_generator = gen


def get_path_generator() -> PathGenerator:
    """Return the active path generator (custom or default)."""
    return _custom_path_generator if _custom_path_generator is not None else DefaultPathGenerator()


__all__ = [
    "DefaultPathGenerator",
    "PathGenerator",
    "get_path_generator",
    "set_path_generator",
]
