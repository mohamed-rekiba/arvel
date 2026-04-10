"""Tests for Spatie Media Library feature parity.

Covers: fluent MediaAdder, custom properties (dot notation), ordering,
single_file / max_items, fallback URLs, collection-except deletion,
get_all_media, get_first/last_media, events, regeneration, accept_file,
conversion.should_apply_to, and human_readable_size.
"""

from __future__ import annotations

import io
from typing import Any

import pytest
from PIL import Image

from arvel.media.adder import MediaAdder
from arvel.media.config import MediaSettings
from arvel.media.events import (
    CollectionHasBeenCleared,
    ConversionHasBeenCompleted,
    ConversionWillStart,
    MediaHasBeenAdded,
)
from arvel.media.fakes import MediaFake
from arvel.media.types import Conversion, Media, MediaCollection


def _jpeg(w: int = 100, h: int = 100) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "red").save(buf, "JPEG", quality=90)
    return buf.getvalue()


# ── Custom properties (dot-notation) ───────────────────────


class TestCustomProperties:
    def test_set_and_get(self) -> None:
        m = Media()
        m.set_custom_property("color", "red")
        assert m.get_custom_property("color") == "red"

    def test_has_custom_property(self) -> None:
        m = Media(custom_properties={"color": "red"})
        assert m.has_custom_property("color") is True
        assert m.has_custom_property("size") is False

    def test_dot_notation_nested(self) -> None:
        m = Media()
        m.set_custom_property("group.primary", "blue")
        assert m.has_custom_property("group.primary") is True
        assert m.get_custom_property("group.primary") == "blue"

    def test_forget_custom_property(self) -> None:
        m = Media(custom_properties={"color": "red", "size": "large"})
        m.forget_custom_property("color")
        assert m.has_custom_property("color") is False
        assert m.has_custom_property("size") is True

    def test_forget_nested(self) -> None:
        m = Media(custom_properties={"group": {"a": 1, "b": 2}})
        m.forget_custom_property("group.a")
        assert m.has_custom_property("group.a") is False
        assert m.has_custom_property("group.b") is True

    def test_get_default(self) -> None:
        m = Media()
        assert m.get_custom_property("missing", "fallback") == "fallback"
        assert m.get_custom_property("missing") is None


class TestHumanReadableSize:
    @pytest.mark.parametrize(
        ("size", "expected"),
        [
            pytest.param(0, "0 B", id="zero"),
            pytest.param(100, "100 B", id="bytes"),
            pytest.param(1024, "1.0 KB", id="one-kb"),
            pytest.param(1536, "1.5 KB", id="1.5-kb"),
            pytest.param(1048576, "1.0 MB", id="one-mb"),
            pytest.param(1073741824, "1.0 GB", id="one-gb"),
        ],
    )
    def test_human_readable(self, size: int, expected: str) -> None:
        m = Media(size=size)
        assert m.human_readable_size == expected


# ── Fluent MediaAdder ────────────────────────────────────────


class TestMediaAdder:
    async def test_fluent_api_sets_name_and_properties(self) -> None:
        fake = MediaFake()
        model = {"type": "User", "id": 1}

        media = await (
            MediaAdder(fake, model, b"data", "photo.jpg", content_type="image/jpeg")
            .using_name("Profile Photo")
            .with_custom_properties({"alt": "avatar"})
            .to_media_collection("avatars")
        )

        assert media.name == "Profile Photo"
        assert media.get_custom_property("alt") == "avatar"
        assert media.collection == "avatars"

    async def test_using_file_name_overrides_filename(self) -> None:
        fake = MediaFake()
        model = {"type": "User", "id": 1}

        media = await (
            MediaAdder(fake, model, b"data", "original.jpg")
            .using_file_name("renamed.jpg")
            .to_media_collection()
        )

        assert "renamed.jpg" in media.filename

    async def test_without_conversions_skips_processing(self) -> None:
        fake = MediaFake()
        fake.register_collection(
            dict,
            MediaCollection(
                name="avatars",
                conversions=[Conversion(name="thumb", width=50, height=50)],
            ),
        )
        model = {"type": "User", "id": 1}

        media = await (
            MediaAdder(fake, model, b"img", "photo.jpg", content_type="image/jpeg")
            .without_conversions()
            .to_media_collection("avatars")
        )

        assert media.conversions == {}

    async def test_with_order(self) -> None:
        fake = MediaFake()
        model = {"type": "User", "id": 1}

        media = await (
            MediaAdder(fake, model, b"data", "photo.jpg").with_order(42).to_media_collection()
        )

        assert media.order_column == 42

    async def test_default_name_from_filename(self) -> None:
        fake = MediaFake()
        model = {"type": "User", "id": 1}

        media = await MediaAdder(fake, model, b"data", "photo.jpg").to_media_collection()

        assert media.name == "photo"


# ── Single file collections ──────────────────────────────────


class TestSingleFileCollection:
    async def test_single_file_replaces_previous(self) -> None:
        fake = MediaFake()
        fake.register_collection(dict, MediaCollection(name="avatar", single_file=True))
        model = {"type": "User", "id": 1}

        first = await fake.add(model, b"a", "a.jpg", collection="avatar")
        second = await fake.add(model, b"b", "b.jpg", collection="avatar")

        items = await fake.get_media(model, "avatar")
        assert len(items) == 1
        assert items[0].id == second.id
        assert first.id != second.id


class TestMaxItemsCollection:
    async def test_max_items_keeps_latest(self) -> None:
        fake = MediaFake()
        fake.register_collection(dict, MediaCollection(name="gallery", max_items=2))
        model = {"type": "User", "id": 1}

        await fake.add(model, b"1", "1.jpg", collection="gallery")
        await fake.add(model, b"2", "2.jpg", collection="gallery")
        third = await fake.add(model, b"3", "3.jpg", collection="gallery")

        items = await fake.get_media(model, "gallery")
        assert len(items) == 2
        ids = [m.id for m in items]
        assert third.id in ids


# ── Fallback URLs ────────────────────────────────────────────


class TestFallbackUrls:
    async def test_fallback_url_when_no_media(self) -> None:
        fake = MediaFake()
        fake.register_collection(dict, MediaCollection(name="avatar", fallback_url="/default.jpg"))
        model = {"type": "User", "id": 1}

        url = await fake.get_first_url(model, "avatar")
        assert url == "/default.jpg"

    async def test_fallback_url_per_conversion(self) -> None:
        fake = MediaFake()
        fake.register_collection(
            dict,
            MediaCollection(
                name="avatar",
                fallback_url="/default.jpg",
                fallback_urls={"thumb": "/default_thumb.jpg"},
            ),
        )
        model = {"type": "User", "id": 1}

        url = await fake.get_first_url(model, "avatar", conversion="thumb")
        assert url == "/default_thumb.jpg"

    async def test_no_fallback_returns_none(self) -> None:
        fake = MediaFake()
        model = {"type": "User", "id": 1}

        url = await fake.get_first_url(model, "empty")
        assert url is None


# ── Retrieval ────────────────────────────────────────────────


class TestRetrieval:
    async def test_get_all_media_across_collections(self) -> None:
        fake = MediaFake()
        model = {"type": "User", "id": 1}

        await fake.add(model, b"1", "a.jpg", collection="avatars")
        await fake.add(model, b"2", "b.jpg", collection="documents")

        all_items = await fake.get_all_media(model)
        assert len(all_items) == 2

    async def test_get_first_media(self) -> None:
        fake = MediaFake()
        model = {"type": "User", "id": 1}

        first = await fake.add(model, b"1", "a.jpg")
        await fake.add(model, b"2", "b.jpg")

        result = await fake.get_first_media(model)
        assert result is not None
        assert result.id == first.id

    async def test_get_last_media(self) -> None:
        fake = MediaFake()
        model = {"type": "User", "id": 1}

        await fake.add(model, b"1", "a.jpg")
        last = await fake.add(model, b"2", "b.jpg")

        result = await fake.get_last_media(model)
        assert result is not None
        assert result.id == last.id

    async def test_get_first_media_returns_none_when_empty(self) -> None:
        fake = MediaFake()
        model = {"type": "User", "id": 1}
        assert await fake.get_first_media(model) is None

    async def test_filter_by_custom_properties_dict(self) -> None:
        fake = MediaFake()
        model = {"type": "User", "id": 1}

        await fake.add(model, b"1", "a.jpg", custom_properties={"color": "red"})
        await fake.add(model, b"2", "b.jpg", custom_properties={"color": "blue"})

        items = await fake.get_media(model, filters={"color": "red"})
        assert len(items) == 1
        assert items[0].get_custom_property("color") == "red"

    async def test_filter_by_callback(self) -> None:
        fake = MediaFake()
        model = {"type": "User", "id": 1}

        await fake.add(model, b"1", "a.jpg", custom_properties={"public": True})
        await fake.add(model, b"2", "b.jpg", custom_properties={"public": False})

        items = await fake.get_media(
            model, filters=lambda m: m.get_custom_property("public") is True
        )
        assert len(items) == 1


# ── Ordering ─────────────────────────────────────────────────


class TestOrdering:
    async def test_set_new_order(self) -> None:
        fake = MediaFake()
        model = {"type": "User", "id": 1}

        m1 = await fake.add(model, b"1", "a.jpg")
        m2 = await fake.add(model, b"2", "b.jpg")
        m3 = await fake.add(model, b"3", "c.jpg")
        assert m1.id is not None and m2.id is not None and m3.id is not None

        await fake.set_new_order([m3.id, m1.id, m2.id])

        items = await fake.get_media(model)
        assert [m.id for m in items] == [m3.id, m1.id, m2.id]

    async def test_order_column_on_add(self) -> None:
        fake = MediaFake()
        model = {"type": "User", "id": 1}

        m = await fake.add(model, b"1", "a.jpg", order=99)
        assert m.order_column == 99


# ── Collection-except deletion ───────────────────────────────


class TestClearCollectionExcept:
    async def test_clears_all_except_specified(self) -> None:
        fake = MediaFake()
        model = {"type": "User", "id": 1}

        m1 = await fake.add(model, b"1", "a.jpg", collection="photos")
        await fake.add(model, b"2", "b.jpg", collection="photos")
        await fake.add(model, b"3", "c.jpg", collection="photos")
        assert m1.id is not None

        removed = await fake.clear_media_collection_except(model, "photos", keep=[m1.id])

        assert removed == 2
        items = await fake.get_media(model, "photos")
        assert len(items) == 1
        assert items[0].id == m1.id


# ── Registered collections ───────────────────────────────────


class TestRegisteredCollections:
    def test_get_registered_collections(self) -> None:
        fake = MediaFake()
        fake.register_collection(dict, MediaCollection(name="avatars"))
        fake.register_collection(dict, MediaCollection(name="docs"))
        fake.register_collection(str, MediaCollection(name="other"))

        result = fake.get_registered_collections(dict)
        names = {c.name for c in result}
        assert names == {"avatars", "docs"}


# ── accept_file callback ────────────────────────────────────


class TestAcceptFileCallback:
    async def test_accept_file_rejects(self) -> None:
        fake = MediaFake()
        fake.register_collection(
            dict,
            MediaCollection(
                name="jpegs",
                accept_file=lambda _f, _c, ct: ct == "image/jpeg",
            ),
        )
        model = {"type": "User", "id": 1}

        from arvel.media.exceptions import MediaValidationError

        with pytest.raises(MediaValidationError, match="accept_file"):
            await fake.add(model, b"png", "f.png", collection="jpegs", content_type="image/png")


# ── Conversion.should_apply_to ───────────────────────────────


class TestConversionCollections:
    def test_applies_to_all_when_no_collections(self) -> None:
        c = Conversion(name="thumb", width=50, height=50)
        assert c.should_apply_to("anything") is True

    def test_applies_only_to_listed_collections(self) -> None:
        c = Conversion(name="thumb", width=50, height=50, collections=["images"])
        assert c.should_apply_to("images") is True
        assert c.should_apply_to("documents") is False


# ── Regeneration ─────────────────────────────────────────────


class TestRegeneration:
    async def test_regenerate_conversions_updates_media(self) -> None:
        fake = MediaFake()
        fake.register_collection(
            dict,
            MediaCollection(
                name="photos",
                conversions=[Conversion(name="thumb", width=50, height=50)],
            ),
        )
        model = {"type": "User", "id": 1}

        media = await fake.add(
            model,
            b"img",
            "photo.jpg",
            collection="photos",
            content_type="image/jpeg",
            process=False,
        )
        assert media.conversions == {}

        updated = await fake.regenerate_conversions(model, "photos")
        assert len(updated) == 1
        assert "thumb" in updated[0].conversions


# ── Delete media with conversions ────────────────────────────


class TestDeleteWithConversions:
    async def test_delete_media_cleans_conversions_from_storage(self) -> None:
        storage = _FakeStorage()
        settings = MediaSettings()
        from arvel.media.manager import MediaManager

        manager = MediaManager(storage=storage, settings=settings)  # ty: ignore[invalid-argument-type]
        manager.register_collection(
            dict,
            MediaCollection(
                name="avatars",
                conversions=[Conversion(name="thumb", width=50, height=50)],
            ),
        )

        model = {"type": "User", "id": 1}
        media = await manager.add(
            model,
            _jpeg(),
            "photo.jpg",
            collection="avatars",
            content_type="image/jpeg",
        )

        stored_count_before = len(storage.stored)
        assert stored_count_before == 2  # original + 1 conversion

        await manager.delete_media(media)
        assert len(storage.stored) == 0


# ── Events ───────────────────────────────────────────────────


class TestMediaEvents:
    async def test_media_has_been_added_event(self) -> None:
        storage = _FakeStorage()
        settings = MediaSettings()
        from arvel.media.manager import MediaManager

        manager = MediaManager(storage=storage, settings=settings)  # ty: ignore[invalid-argument-type]
        events: list[Any] = []
        manager.on_event(events.append)

        model = {"type": "User", "id": 1}
        await manager.add(model, b"data", "f.txt")

        assert len(events) == 1
        assert isinstance(events[0], MediaHasBeenAdded)

    async def test_collection_cleared_event(self) -> None:
        storage = _FakeStorage()
        settings = MediaSettings()
        from arvel.media.manager import MediaManager

        manager = MediaManager(storage=storage, settings=settings)  # ty: ignore[invalid-argument-type]
        events: list[Any] = []
        manager.on_event(events.append)

        model = {"type": "User", "id": 1}
        await manager.add(model, b"data", "f.txt", collection="docs")
        events.clear()

        await manager.delete_all(model, collection="docs")

        assert any(isinstance(e, CollectionHasBeenCleared) for e in events)

    async def test_conversion_events_on_regenerate(self) -> None:
        storage = _FakeStorage()
        settings = MediaSettings()
        from arvel.media.manager import MediaManager

        manager = MediaManager(storage=storage, settings=settings)  # ty: ignore[invalid-argument-type]
        manager.register_collection(
            dict,
            MediaCollection(
                name="photos",
                conversions=[Conversion(name="thumb", width=50, height=50)],
            ),
        )
        events: list[Any] = []
        manager.on_event(events.append)

        model = {"type": "User", "id": 1}
        await manager.add(
            model,
            _jpeg(),
            "photo.jpg",
            collection="photos",
            content_type="image/jpeg",
        )

        events.clear()
        storage.data[next(iter(storage.data.keys()))] = _jpeg()

        await manager.regenerate_conversions(model, "photos")

        assert any(isinstance(e, ConversionWillStart) for e in events)
        assert any(isinstance(e, ConversionHasBeenCompleted) for e in events)


# ── UUID ─────────────────────────────────────────────────────


class TestMediaUuid:
    async def test_media_has_uuid(self) -> None:
        fake = MediaFake()
        model = {"type": "User", "id": 1}
        media = await fake.add(model, b"data", "f.txt")
        assert len(media.uuid) == 36  # UUID4 format


# ── Helpers ──────────────────────────────────────────────────


class _FakeStorage:
    def __init__(self) -> None:
        self.stored: list[tuple[str, bytes, str | None]] = []
        self.data: dict[str, bytes] = {}

    async def put(self, path: str, data: bytes, *, content_type: str | None = None) -> None:
        self.stored.append((path, data, content_type))
        self.data[path] = data

    async def url(self, path: str) -> str:
        return f"/storage/{path}"

    async def delete(self, path: str) -> None:
        self.stored = [(p, d, ct) for p, d, ct in self.stored if p != path]
        self.data.pop(path, None)

    async def get(self, path: str) -> bytes | None:
        return self.data.get(path)
