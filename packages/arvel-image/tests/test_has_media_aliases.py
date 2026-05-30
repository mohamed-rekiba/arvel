"""WI-arvel-036 / FR-036-04 + FR-036-05 — HasMedia aliases + HasMediaMixin QA-Pre tests.

All tests in this file should FAIL until Stage 3b adds:
- ``HasMedia.attach_media()`` alias for ``add_media().to_media_collection()``
- ``HasMedia.delete_media()`` alias for ``clear_media_collection()``
- ``HasMediaMixin = HasMedia`` re-export in ``arvel_image/__init__.py``
"""

from __future__ import annotations

import inspect
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("arvel_image", reason="arvel_image required for WI-arvel-036 tests")


# ── FR-036-05: HasMediaMixin export ──────────────────────────────────────────


def test_has_media_mixin_is_exported() -> None:
    """FR-036-05a: from arvel_image import HasMediaMixin resolves without error."""
    # This import must succeed — if HasMediaMixin is not exported it raises ImportError
    import arvel_image

    assert arvel_image.HasMediaMixin is not None, "HasMediaMixin resolved to None"
    assert arvel_image.HasMedia is not None, "HasMedia must remain exported"


def test_has_media_mixin_is_has_media() -> None:
    """FR-036-05a: HasMediaMixin resolves to the same class as HasMedia."""
    from arvel_image import (
        HasMedia,
        HasMediaMixin,
    )

    assert HasMediaMixin is HasMedia


# ── FR-036-04a: attach_media() exists ────────────────────────────────────────


def test_attach_media_method_exists() -> None:
    """FR-036-04a: HasMedia exposes attach_media()."""
    from arvel_image import HasMedia

    assert hasattr(HasMedia, "attach_media"), "HasMedia.attach_media not found"
    assert callable(HasMedia.attach_media)


def test_attach_media_accepts_collection_param() -> None:
    """FR-036-04a: attach_media signature includes collection kwarg."""
    from arvel_image import HasMedia

    sig = inspect.signature(HasMedia.attach_media)
    params = set(sig.parameters.keys())

    assert "source" in params
    assert "collection" in params or "file_name" in params


def test_attach_media_is_a_coroutine() -> None:
    """FR-036-04a: attach_media must be awaitable (returns a coroutine)."""
    from arvel_image import HasMedia

    assert inspect.iscoroutinefunction(HasMedia.attach_media), (
        "attach_media is not a coroutine function — it must be async"
    )


# ── FR-036-04b: delete_media() exists ────────────────────────────────────────


def test_delete_media_method_exists() -> None:
    """FR-036-04b: HasMedia exposes delete_media()."""
    from arvel_image import HasMedia

    assert hasattr(HasMedia, "delete_media"), "HasMedia.delete_media not found"
    assert callable(HasMedia.delete_media)


def test_delete_media_is_a_coroutine() -> None:
    """FR-036-04b: delete_media must be awaitable."""
    from arvel_image import HasMedia

    assert inspect.iscoroutinefunction(HasMedia.delete_media), (
        "delete_media is not a coroutine function — it must be async"
    )


def test_delete_media_signature_has_collection_param() -> None:
    """FR-036-04b: delete_media(collection='default') mirrors clear_media_collection."""
    from arvel_image import HasMedia

    sig = inspect.signature(HasMedia.delete_media)
    params = sig.parameters

    assert "collection" in params
    default = params["collection"].default
    assert default == "default"


# ── FR-036-04c: aliases delegate, no new logic ───────────────────────────────


@pytest.mark.asyncio
async def test_delete_media_delegates_to_clear_media_collection() -> None:
    """FR-036-04c: delete_media delegates to clear_media_collection."""
    from arvel_image import HasMedia

    class FakeHost(HasMedia):
        id = 1
        captured_collection: str = ""

        async def clear_media_collection(self, collection: str = "default") -> int:
            self.captured_collection = collection
            return 3

    host = FakeHost()
    count = await host.delete_media("gallery")

    assert count == 3
    assert host.captured_collection == "gallery"


@pytest.mark.asyncio
async def test_attach_media_delegates_to_add_media_chain() -> None:
    """FR-036-04c: attach_media delegates to add_media().to_media_collection()."""
    from arvel_image import HasMedia
    from arvel_image.media.model import Media

    fake_media = MagicMock(spec=Media)

    class FakeHost(HasMedia):
        id = 1
        captured_source: Any = None
        captured_file_name: str | None = None

        def add_media(self, source: Any, *, file_name: str | None = None) -> Any:
            self.captured_source = source
            self.captured_file_name = file_name

            adder = MagicMock()
            adder.to_media_collection = AsyncMock(return_value=fake_media)
            return adder

    host = FakeHost()
    result = await host.attach_media(b"data", file_name="x.jpg", collection="gallery")

    assert result is fake_media
    assert host.captured_source == b"data"
    assert host.captured_file_name == "x.jpg"


# ── FR-036-05b: no deprecation warnings ──────────────────────────────────────


def test_has_media_mixin_import_no_warnings() -> None:
    """FR-036-05b: importing HasMediaMixin emits no DeprecationWarning."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        try:
            import arvel_image

            _ = arvel_image.HasMediaMixin
        except ImportError:
            pytest.fail("HasMediaMixin not importable")
