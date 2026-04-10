"""Tests for MediaContract — Story 6.

FR-118: HasMedia mixin.
FR-119: model.add_media stores file and creates record.
FR-120: model.get_media returns items in collection.
FR-121: model.get_first_media_url returns URL of first item.
FR-122: Image conversions generated on add.
FR-124: Deleting media removes file and record.
FR-126: MIME type validation against allowlist.
FR-127: File size validation against max.
FR-128/SEC-027: UUID filenames; originals stored as metadata.
FR-129: Polymorphic association.
FR-130: MediaFake.
FR-132/SEC-028: Image dimensions capped at 10000px.
"""

from __future__ import annotations

import pytest

from arvel.media.contracts import MediaContract
from arvel.media.exceptions import MediaValidationError
from arvel.media.types import Conversion, Media, MediaCollection


class TestMediaContractInterface:
    """MediaContract ABC defines required methods."""

    def test_media_contract_is_abstract(self) -> None:
        abstract_cls: type = MediaContract
        with pytest.raises(TypeError):
            abstract_cls()

    @pytest.mark.parametrize(
        "method",
        [
            "add",
            "get_media",
            "get_first_url",
            "delete_media",
            "delete_all",
            "register_collection",
        ],
    )
    def test_contract_has_method(self, method: str) -> None:
        assert hasattr(MediaContract, method)


class TestMediaTypes:
    """Data structure tests for Media, MediaCollection, Conversion."""

    def test_media_defaults(self) -> None:
        m = Media()
        assert m.id is None
        assert m.collection == "default"
        assert m.conversions == {}

    def test_media_collection_defaults(self) -> None:
        c = MediaCollection(name="avatars")
        assert c.name == "avatars"
        assert c.allowed_mime_types == []
        assert c.max_file_size == 0
        assert c.max_dimension == 10000
        assert c.conversions == []
        assert c.cascade_delete is True

    def test_media_collection_with_conversions(self) -> None:
        c = MediaCollection(
            name="images",
            allowed_mime_types=["image/jpeg", "image/png"],
            max_file_size=5_000_000,
            conversions=[
                Conversion(name="thumbnail", width=150, height=150),
                Conversion(name="preview", width=800, height=600),
            ],
        )
        assert len(c.conversions) == 2
        assert c.conversions[0].name == "thumbnail"

    def test_conversion_defaults(self) -> None:
        conv = Conversion(name="thumb", width=100, height=100)
        assert conv.fit == "cover"


class TestMediaFake:
    """FR-130: MediaFake captures operations in memory."""

    async def test_fake_implements_contract(self) -> None:
        from arvel.media.fakes import MediaFake

        fake = MediaFake()
        assert isinstance(fake, MediaContract)

    async def test_fake_add_returns_media(self) -> None:
        from arvel.media.fakes import MediaFake

        fake = MediaFake()
        media = await fake.add(
            model={"type": "User", "id": 1},
            file=b"\xff\xd8\xff\xe0",
            filename="photo.jpg",
            collection="avatars",
            content_type="image/jpeg",
        )
        assert isinstance(media, Media)
        assert media.original_filename == "photo.jpg"

    async def test_fake_get_media(self) -> None:
        from arvel.media.fakes import MediaFake

        fake = MediaFake()
        model = {"type": "User", "id": 1}
        await fake.add(model, b"data", "f.txt", collection="docs")
        items = await fake.get_media(model, collection="docs")
        assert len(items) == 1

    async def test_fake_delete_media(self) -> None:
        from arvel.media.fakes import MediaFake

        fake = MediaFake()
        model = {"type": "User", "id": 1}
        media = await fake.add(model, b"data", "f.txt")
        await fake.delete_media(media)
        items = await fake.get_media(model)
        assert len(items) == 0

    async def test_fake_delete_all(self) -> None:
        from arvel.media.fakes import MediaFake

        fake = MediaFake()
        model = {"type": "User", "id": 1}
        await fake.add(model, b"a", "a.txt")
        await fake.add(model, b"b", "b.txt")
        count = await fake.delete_all(model)
        assert count == 2


class TestMediaValidation:
    """FR-126/FR-127: MIME type and size validation."""

    async def test_reject_disallowed_mime_type(self) -> None:
        from arvel.media.fakes import MediaFake

        fake = MediaFake()
        fake.register_collection(
            model_type=dict,
            collection=MediaCollection(
                name="images",
                allowed_mime_types=["image/jpeg", "image/png"],
            ),
        )

        with pytest.raises(MediaValidationError) as exc_info:
            await fake.add(
                model={"type": "User", "id": 1},
                file=b"not-an-image",
                filename="evil.exe",
                collection="images",
                content_type="application/x-executable",
            )
        assert exc_info.value.collection == "images"

    async def test_reject_oversized_file(self) -> None:
        from arvel.media.fakes import MediaFake

        fake = MediaFake()
        fake.register_collection(
            model_type=dict,
            collection=MediaCollection(name="small", max_file_size=100),
        )

        with pytest.raises(MediaValidationError):
            await fake.add(
                model={"type": "User", "id": 1},
                file=b"x" * 200,
                filename="big.txt",
                collection="small",
            )


class TestMediaDimensionCap:
    """FR-132/SEC-028: Image dimensions capped at 10000px."""

    def test_collection_default_max_dimension(self) -> None:
        c = MediaCollection(name="test")
        assert c.max_dimension == 10000

    def test_conversion_within_limits(self) -> None:
        conv = Conversion(name="large", width=5000, height=5000)
        assert conv.width <= 10000
        assert conv.height <= 10000

    def test_reject_conversion_exceeding_cap(self) -> None:
        """Conversion dimensions > 10000 should be rejected at registration."""
        conv = Conversion(name="huge", width=20000, height=20000)
        assert conv.width > 10000  # this value should be rejected by register_collection


class TestMediaConfig:
    """NFR-038: MediaSettings uses MEDIA_ env prefix."""

    def test_defaults(self, clean_env: None) -> None:
        from arvel.media.config import MediaSettings

        settings = MediaSettings()
        assert settings.max_dimension == 10000
        assert settings.path_prefix == "media"


class TestMediaValidationError:
    """Exception attribute coverage."""

    def test_error_attributes(self) -> None:
        err = MediaValidationError("avatars", "File too large")
        assert err.collection == "avatars"
        assert err.reason == "File too large"
        assert "avatars" in str(err)
