"""HasMedia public surface — the one-method DX after the cleanup."""

from __future__ import annotations

import inspect

import pytest

pytest.importorskip("arvel_image", reason="arvel_image required")


# ── add_image: the polymorphic upload ────────────────────────────────


def test_add_image_method_exists() -> None:
    from arvel_image import HasMedia

    assert callable(getattr(HasMedia, "add_image", None))


def test_add_image_is_a_coroutine() -> None:
    from arvel_image import HasMedia

    assert inspect.iscoroutinefunction(HasMedia.add_image)


def test_add_image_collection_kwarg_defaults_to_none() -> None:
    """add_image accepts optional collection= for multi-collection hosts; default = None."""
    from arvel_image import HasMedia

    params = inspect.signature(HasMedia.add_image).parameters
    assert "source" in params
    assert "file_name" in params
    assert "collection" in params
    assert params["collection"].default is None


# ── image_builder: the advanced builder ──────────────────────────────


def test_image_builder_method_exists() -> None:
    from arvel_image import HasMedia

    assert callable(getattr(HasMedia, "image_builder", None))


def test_image_builder_is_synchronous() -> None:
    """image_builder returns a FileAdder synchronously; .save() is the async tail."""
    from arvel_image import HasMedia

    assert not inspect.iscoroutinefunction(HasMedia.image_builder)


# ── clear_images: drop the collection ────────────────────────────────


def test_clear_images_method_exists() -> None:
    from arvel_image import HasMedia

    assert callable(getattr(HasMedia, "clear_images", None))


def test_clear_images_is_a_coroutine() -> None:
    from arvel_image import HasMedia

    assert inspect.iscoroutinefunction(HasMedia.clear_images)


def test_clear_images_takes_no_collection_param() -> None:
    """clear_images uses __media_collection__; multi-collection callers use clear_media_in."""
    from arvel_image import HasMedia

    params = inspect.signature(HasMedia.clear_images).parameters
    # `self` only.
    assert list(params.keys()) == ["self"]


# ── default collection: singular string ──────────────────────────────


def test_media_collection_is_a_string_default() -> None:
    from arvel_image import HasMedia

    assert HasMedia.__media_collection__ == "default"
    assert isinstance(HasMedia.__media_collection__, str)


# ── documented public API exists ───────────────────────────────────────
#
# Catches doc drift: every method listed in the README method tables must
# exist on the live class. If you rename a method, this test must change too
# — and you'll remember to update the README in the same PR.


def _public_methods(cls: type) -> set[str]:
    return {n for n, _ in inspect.getmembers(cls, callable) if not n.startswith("_")}


def test_image_documented_methods_exist() -> None:
    """README's `Image` operations table."""
    from arvel_image import Image

    documented = {
        "load",
        "fit",
        "resize",
        "crop",
        "to_width",
        "to_height",
        "format",
        "quality",
        "optimize",
        "strip_exif",
        "save",
        "save_async",
        "to_bytes",
        "to_bytes_async",
    }
    members = _public_methods(Image)
    missing = documented - members
    assert not missing, f"README mentions undefined Image methods: {sorted(missing)}"


def test_conversion_documented_methods_exist() -> None:
    """README's `Conversion` chain methods table."""
    from arvel_image.media import Conversion

    documented = {
        "fit",
        "resize",
        "crop",
        "to_width",
        "to_height",
        "format",
        "quality",
        "generate_responsive_images",
        "with_manipulations",
        "accepts",
        "apply",
    }
    members = _public_methods(Conversion)
    missing = documented - members
    assert not missing, f"README mentions undefined Conversion methods: {sorted(missing)}"


def test_media_collection_documented_methods_exist() -> None:
    """README's `MediaCollection` reference."""
    from arvel_image.media import MediaCollection

    documented = {
        "with_conversions",
        "single_file",
        "use_disk",
        "use_conversions_disk",
        "accept_mime_types",
        "max_file_size",
        "only_keep_latest",
        "use_fallback_url",
        "generate_responsive_images",
        "accepts_file",
        "register_on",
    }
    members = _public_methods(MediaCollection)
    missing = documented - members
    assert not missing, f"README mentions undefined MediaCollection methods: {sorted(missing)}"


def test_has_media_documented_methods_exist() -> None:
    """README's `HasMedia` public surface."""
    from arvel_image import HasMedia

    documented = {
        "add_image",
        "image_builder",
        "get_media",
        "media_in",
        "clear_images",
        "clear_media_in",
        "clear_media_in_except",
        "image_url",
        "collection_for",
        "host_pk",
        "register_media_collections",
        "delete_preserving_media",
        "to_dict",
    }
    members = _public_methods(HasMedia)
    missing = documented - members
    assert not missing, f"README mentions undefined HasMedia methods: {sorted(missing)}"


def test_media_documented_methods_exist() -> None:
    """README + docs/ Media row methods."""
    from arvel_image import Media

    documented = {
        "url",
        "full_url",
        "srcset",
        "all_srcsets",
        "placeholder_svg",
        "temporary_url",
        "conversion_urls",
        "has_generated_conversion",
        "get_path",
        "to_dict",
        "delete",
        "copy",
        "move",
        "has_custom_property",
        "get_custom_property",
        "set_custom_property",
        "forget_custom_property",
        "set_new_order",
    }
    members = _public_methods(Media)
    missing = documented - members
    assert not missing, f"README/docs mention undefined Media methods: {sorted(missing)}"
