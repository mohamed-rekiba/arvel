"""Declarative image conversion (chain of :class:`arvel_image.Image` ops).

A ``Conversion`` is just a name plus an ordered list of operations to apply
to an :class:`arvel_image.Image`. Each chain call (``fit``, ``resize``,
``crop``, ``quality``, ``format``) appends an operation; nothing runs until
:meth:`apply` is called by the conversion runner. ``accepts(mime_type)``
gates which sources a conversion will run against — defaults to ``image/*``
so applying an image conversion to a PDF silently skips, matching Spatie.

Subclasses can override ``apply`` for fully bespoke pipelines (handy for
tests). The default ``apply`` walks the recorded chain in order.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from arvel_image.image import Image

# Supported manipulation keys and the Conversion methods they map to.
# Applied by with_manipulations() in the order below so geometry comes
# before quality/format (matching Spatie's apply order).
_MANIP_ORDER = ("fit", "resize", "quality", "format")

# Each recorded op is a (method_name, args). Args are either positional
# (tuple) or keyword (dict) — we keep both forms because ``Image.fit`` is
# positional while ``Image.resize`` / ``Image.crop`` are keyword-only.
_Op = tuple[str, tuple[Any, ...] | dict[str, Any]]


class Conversion:
    """A declarative chain of operations applied to an image source."""

    def __init__(self, name: str) -> None:
        if not name:
            msg = "Conversion name must be a non-empty string"
            raise ValueError(msg)
        self.name = name
        self._ops: list[_Op] = []
        self._target_format: str | None = None
        self._responsive_images: bool = False

    # ─── chain ─────────────────────────────────────────────────────────────

    def fit(self, mode: str, width: int, height: int) -> Self:
        """Fit into ``(width, height)`` using ``cover`` or ``contain``."""
        self._ops.append(("fit", (mode, width, height)))
        return self

    def resize(self, *, width: int, height: int) -> Self:
        """Stretch to ``(width, height)`` exactly."""
        self._ops.append(("resize", {"width": width, "height": height}))
        return self

    def crop(self, *, left: int, top: int, width: int, height: int) -> Self:
        """Crop to ``(width, height)`` starting at ``(left, top)``."""
        self._ops.append(("crop", {"left": left, "top": top, "width": width, "height": height}))
        return self

    def quality(self, value: int) -> Self:
        """Output quality (1..100), honoured by JPEG and WEBP."""
        self._ops.append(("quality", (value,)))
        return self

    def format(self, image_format: str) -> Self:
        """Change the output format (jpeg/png/webp/gif)."""
        self._target_format = image_format
        self._ops.append(("format", (image_format,)))
        return self

    def generate_responsive_images(self) -> Self:
        """Generate srcset width variants from this conversion's output.

        Works the same as ``MediaCollection.generate_responsive_images()`` but
        scoped to one conversion: variants are stored under the conversion name
        key (e.g. ``"thumb"``) in ``media.responsive_images`` so
        ``media.get_srcset("thumb")`` returns them.
        """
        self._responsive_images = True
        return self

    @property
    def responsive_images_enabled(self) -> bool:
        """True when this conversion should generate responsive width variants."""
        return self._responsive_images

    # ─── execution ─────────────────────────────────────────────────────────

    def with_manipulations(self, overrides: dict[str, Any]) -> Conversion:
        """Return a shallow copy of this conversion with ``overrides`` appended.

        Supported keys: ``fit`` (mode string), ``width`` (int), ``height`` (int),
        ``quality`` (int), ``format`` (str). Geometry ops are applied before
        quality/format so they compose predictably.

        The original conversion is never mutated — safe to call in a loop.
        """
        if not overrides:
            return self
        patched = Conversion(self.name)
        patched._ops = list(self._ops)
        patched._target_format = self._target_format
        patched._responsive_images = self._responsive_images
        w = overrides.get("width")
        h = overrides.get("height")
        fit_mode = overrides.get("fit")
        if fit_mode and w and h:
            patched.fit(str(fit_mode), int(w), int(h))
        elif w and h:
            patched.resize(width=int(w), height=int(h))
        if "quality" in overrides:
            patched.quality(int(overrides["quality"]))
        if "format" in overrides:
            patched.format(str(overrides["format"]))
        return patched

    def accepts(self, mime_type: str | None) -> bool:
        """Default mime filter: only ``image/*``. Override for richer rules."""
        return mime_type is not None and mime_type.startswith("image/")

    def apply(self, source: Image) -> Image:
        """Run the recorded chain against ``source`` and return the result.

        Mutates the underlying Pillow image in place (``Image`` operations
        return ``self``), but the returned ``Image`` is the same instance —
        consumers should treat it as a fresh derivation.
        """
        out = source
        for method_name, args in self._ops:
            method = getattr(out, method_name)
            out = method(*args) if isinstance(args, tuple) else method(**args)
        return out


__all__ = ["Conversion"]
