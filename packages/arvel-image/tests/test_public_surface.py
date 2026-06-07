"""Pin the 1.0 public surface of `arvel_image` and `arvel_image.media`.

Stability commitment: every name in `__all__` here is something we'll keep
stable through the 1.0 line. Demoting a name from `__all__` is a breaking
change; promoting one is a soft commitment. If you break this test on
purpose, update both `__all__` lists *and* `docs/packages/image.md`'s
public-surface enumeration in the same change.
"""

from __future__ import annotations

import importlib

import pytest

PACKAGE_PUBLIC: frozenset[str] = frozenset(
    {
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
    },
)

# Media subpackage mirrors PACKAGE_PUBLIC minus the names that live elsewhere:
# Image + UnsupportedFormatError + set_max_pixels come from arvel_image.image,
# and ImageServiceProvider from arvel_image.provider.
MEDIA_PUBLIC: frozenset[str] = PACKAGE_PUBLIC - {
    "Image",
    "ImageServiceProvider",
    "UnsupportedFormatError",
    "set_max_pixels",
}

# Demoted in iter 7 — submodule paths stay stable for framework-internal callers.
DEMOTED_TO_SUBMODULE: dict[str, str] = {
    "FileInfo": "arvel_image.media.collection",
    "get_collection_preset": "arvel_image.media.presets",
    "register_collection_preset": "arvel_image.media.presets",
}


def test_package_all_matches_public_surface() -> None:
    pkg = importlib.import_module("arvel_image")
    assert frozenset(pkg.__all__) == PACKAGE_PUBLIC, (
        "arvel_image.__all__ drifted from the 1.0 surface. "
        "If this is intentional, update PACKAGE_PUBLIC and "
        "docs/packages/image.md together."
    )


def test_media_all_matches_public_surface() -> None:
    media = importlib.import_module("arvel_image.media")
    assert frozenset(media.__all__) == MEDIA_PUBLIC, (
        "arvel_image.media.__all__ drifted from the 1.0 surface."
    )


def test_demoted_symbols_not_on_package() -> None:
    pkg = importlib.import_module("arvel_image")
    media = importlib.import_module("arvel_image.media")
    for name in DEMOTED_TO_SUBMODULE:
        assert name not in pkg.__all__, (
            f"{name} was demoted to internal but is still in arvel_image.__all__"
        )
        assert not hasattr(pkg, name), (
            f"{name} was demoted to internal but is still attached to arvel_image"
        )
        assert name not in media.__all__, (
            f"{name} was demoted to internal but is still in arvel_image.media.__all__"
        )
        assert not hasattr(media, name), (
            f"{name} was demoted to internal but is still attached to arvel_image.media"
        )


@pytest.mark.parametrize(("name", "module"), DEMOTED_TO_SUBMODULE.items())
def test_demoted_symbols_still_reachable_via_submodule(name: str, module: str) -> None:
    # Demotion controls the exported surface, not the symbol's existence.
    # Submodule paths stay so framework-internal callers keep working.
    mod = importlib.import_module(module)
    assert hasattr(mod, name), f"{module}.{name} disappeared — that's a real break"
