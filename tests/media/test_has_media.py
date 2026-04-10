"""Tests for HasMedia model mixin — FB-S2-001.

The HasMedia mixin adds media helper methods to any ArvelModel subclass:
- register_media_collections() hook for declaring collections
- media(collection) helper for fetching associated media
- add_media(file, filename, ...) for attaching files
- clear_media(collection) for removing associated files
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from arvel.media.types import Conversion, Media, MediaCollection


class TestHasMediaMixin:
    """FB-S2-001: HasMedia model mixin adds media helpers to ORM models."""

    def test_mixin_provides_register_collections_hook(self) -> None:
        from arvel.media.mixins import HasMedia

        assert hasattr(HasMedia, "register_media_collections")

    def test_mixin_provides_media_method(self) -> None:
        from arvel.media.mixins import HasMedia

        assert hasattr(HasMedia, "media")

    def test_mixin_provides_add_media_method(self) -> None:
        from arvel.media.mixins import HasMedia

        assert hasattr(HasMedia, "add_media")

    def test_mixin_provides_clear_media_method(self) -> None:
        from arvel.media.mixins import HasMedia

        assert hasattr(HasMedia, "clear_media")

    def test_mixin_provides_first_media_url_method(self) -> None:
        from arvel.media.mixins import HasMedia

        assert hasattr(HasMedia, "first_media_url")


class TestHasMediaRegistration:
    """HasMedia.register_media_collections defines collection constraints."""

    def test_register_collections_returns_list(self) -> None:
        from arvel.media.mixins import HasMedia

        class FakeModel(HasMedia):
            pass

        instance = FakeModel.__new__(FakeModel)
        result = instance.register_media_collections()
        assert isinstance(result, list)

    def test_subclass_can_override_collections(self) -> None:
        from arvel.media.mixins import HasMedia

        class UserModel(HasMedia):
            def register_media_collections(self) -> list[MediaCollection]:
                return [
                    MediaCollection(
                        name="avatars",
                        allowed_mime_types=["image/jpeg", "image/png"],
                        max_file_size=5 * 1024 * 1024,
                        conversions=[Conversion(name="thumb", width=150, height=150)],
                    ),
                ]

        instance = UserModel.__new__(UserModel)
        collections = instance.register_media_collections()
        assert len(collections) == 1
        assert collections[0].name == "avatars"
        assert len(collections[0].conversions) == 1


class TestHasMediaOperations:
    """HasMedia delegates to MediaContract for actual file operations."""

    async def test_add_media_delegates_to_contract(self) -> None:
        from arvel.media.mixins import HasMedia

        mock_contract = AsyncMock()
        mock_contract.add.return_value = Media(
            id=1,
            model_type="Post",
            model_id=42,
            collection="images",
            filename="abc-photo.jpg",
            original_filename="photo.jpg",
            mime_type="image/jpeg",
            size=1024,
            disk="local",
            path="media/images/abc-photo.jpg",
        )

        class Post(HasMedia):
            id = 42
            _media_contract = mock_contract

        post = Post.__new__(Post)
        post.id = 42
        post._media_contract = mock_contract

        result = await post.add_media(
            b"jpeg-bytes", "photo.jpg", content_type="image/jpeg"
        ).to_media_collection("images")
        assert result.original_filename == "photo.jpg"
        mock_contract.add.assert_awaited_once()

    async def test_media_returns_items_for_collection(self) -> None:
        from arvel.media.mixins import HasMedia

        mock_contract = AsyncMock()
        mock_contract.get_media.return_value = [
            Media(id=1, model_type="Post", model_id=1, collection="images"),
            Media(id=2, model_type="Post", model_id=1, collection="images"),
        ]

        class Post(HasMedia):
            id = 1
            _media_contract = mock_contract

        post = Post.__new__(Post)
        post.id = 1
        post._media_contract = mock_contract

        items = await post.media("images")
        assert len(items) == 2
        mock_contract.get_media.assert_awaited_once()

    async def test_clear_media_delegates_to_contract(self) -> None:
        from arvel.media.mixins import HasMedia

        mock_contract = AsyncMock()
        mock_contract.delete_all.return_value = 3

        class Post(HasMedia):
            id = 1
            _media_contract = mock_contract

        post = Post.__new__(Post)
        post.id = 1
        post._media_contract = mock_contract

        count = await post.clear_media("images")
        assert count == 3
        mock_contract.delete_all.assert_awaited_once()

    async def test_first_media_url_delegates_to_contract(self) -> None:
        from arvel.media.mixins import HasMedia

        mock_contract = AsyncMock()
        mock_contract.get_first_url.return_value = "/storage/avatars/photo.jpg"

        class Post(HasMedia):
            id = 1
            _media_contract = mock_contract

        post = Post.__new__(Post)
        post.id = 1
        post._media_contract = mock_contract

        url = await post.first_media_url("avatars")
        assert url == "/storage/avatars/photo.jpg"

    async def test_first_media_url_with_conversion(self) -> None:
        from arvel.media.mixins import HasMedia

        mock_contract = AsyncMock()
        mock_contract.get_first_url.return_value = "/storage/avatars/thumb-photo.jpg"

        class Post(HasMedia):
            id = 1
            _media_contract = mock_contract

        post = Post.__new__(Post)
        post.id = 1
        post._media_contract = mock_contract

        url = await post.first_media_url("avatars", conversion="thumb")
        assert url == "/storage/avatars/thumb-photo.jpg"
        mock_contract.get_first_url.assert_awaited_once_with(post, "avatars", "thumb")
