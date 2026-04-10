"""Tests for StorageContract and drivers — Story 3.

FR-088: StorageContract ABC with put, get, delete, exists, url, temporary_url, size, list.
FR-089: put(path, data, content_type) writes bytes.
FR-090: get(path) returns bytes or raises FileNotFoundError.
FR-091: delete(path) removes file and returns bool.
FR-092: exists(path) checks existence.
FR-093: url(path) returns public URL.
FR-095: LocalStorage driver.
FR-097: NullStorage driver.
FR-098: StorageFake.
FR-099/SEC-023: Path sanitization (directory traversal, absolute paths, null bytes).
NFR-036: Security tests for storage paths.
"""

from __future__ import annotations

import pytest

from arvel.storage.contracts import StorageContract
from arvel.storage.exceptions import StoragePathError


class TestStorageContractInterface:
    """FR-088: StorageContract ABC defines required methods."""

    def test_storage_contract_is_abstract(self) -> None:
        abstract_cls: type = StorageContract
        with pytest.raises(TypeError):
            abstract_cls()

    @pytest.mark.parametrize(
        "method",
        [
            "put",
            "get",
            "delete",
            "exists",
            "url",
            "temporary_url",
            "size",
            "list",
        ],
    )
    def test_contract_has_method(self, method: str) -> None:
        assert hasattr(StorageContract, method)


class TestLocalStorageDriver:
    """FR-095: LocalStorage stores files on local filesystem."""

    async def test_local_implements_contract(self) -> None:
        from arvel.storage.drivers.local_driver import LocalStorage

        storage = LocalStorage(root="/tmp/test-storage", base_url="/storage")  # noqa: S108
        assert isinstance(storage, StorageContract)

    async def test_put_and_get(self, tmp_path) -> None:
        from arvel.storage.drivers.local_driver import LocalStorage

        storage = LocalStorage(root=str(tmp_path), base_url="/storage")
        await storage.put("test.txt", b"hello world")
        data = await storage.get("test.txt")
        assert data == b"hello world"

    async def test_get_missing_file_raises(self, tmp_path) -> None:
        from arvel.storage.drivers.local_driver import LocalStorage

        storage = LocalStorage(root=str(tmp_path), base_url="/storage")
        with pytest.raises(FileNotFoundError):
            await storage.get("nonexistent.txt")

    async def test_delete_existing_file(self, tmp_path) -> None:
        from arvel.storage.drivers.local_driver import LocalStorage

        storage = LocalStorage(root=str(tmp_path), base_url="/storage")
        await storage.put("remove-me.txt", b"data")
        removed = await storage.delete("remove-me.txt")
        assert removed is True
        assert await storage.exists("remove-me.txt") is False

    async def test_delete_missing_file(self, tmp_path) -> None:
        from arvel.storage.drivers.local_driver import LocalStorage

        storage = LocalStorage(root=str(tmp_path), base_url="/storage")
        removed = await storage.delete("nope.txt")
        assert removed is False

    async def test_exists(self, tmp_path) -> None:
        from arvel.storage.drivers.local_driver import LocalStorage

        storage = LocalStorage(root=str(tmp_path), base_url="/storage")
        assert await storage.exists("no.txt") is False
        await storage.put("yes.txt", b"data")
        assert await storage.exists("yes.txt") is True

    async def test_url(self, tmp_path) -> None:
        from arvel.storage.drivers.local_driver import LocalStorage

        storage = LocalStorage(root=str(tmp_path), base_url="/storage")
        url = await storage.url("avatars/photo.jpg")
        assert url == "/storage/avatars/photo.jpg"

    async def test_size(self, tmp_path) -> None:
        from arvel.storage.drivers.local_driver import LocalStorage

        storage = LocalStorage(root=str(tmp_path), base_url="/storage")
        await storage.put("sized.txt", b"12345")
        sz = await storage.size("sized.txt")
        assert sz == 5

    async def test_list_files(self, tmp_path) -> None:
        from arvel.storage.drivers.local_driver import LocalStorage

        storage = LocalStorage(root=str(tmp_path), base_url="/storage")
        await storage.put("docs/a.txt", b"a")
        await storage.put("docs/b.txt", b"b")
        files = await storage.list("docs/")
        assert sorted(files) == ["docs/a.txt", "docs/b.txt"]


class TestNullStorageDriver:
    """FR-097: NullStorage discards all writes silently."""

    async def test_null_implements_contract(self) -> None:
        from arvel.storage.drivers.null_driver import NullStorage

        storage = NullStorage()
        assert isinstance(storage, StorageContract)

    async def test_null_put_does_nothing(self) -> None:
        from arvel.storage.drivers.null_driver import NullStorage

        storage = NullStorage()
        await storage.put("file.txt", b"data")

    async def test_null_get_raises_not_found(self) -> None:
        from arvel.storage.drivers.null_driver import NullStorage

        storage = NullStorage()
        with pytest.raises(FileNotFoundError):
            await storage.get("file.txt")

    async def test_null_exists_always_false(self) -> None:
        from arvel.storage.drivers.null_driver import NullStorage

        storage = NullStorage()
        assert await storage.exists("anything") is False


class TestStorageFake:
    """FR-098: StorageFake captures operations for assertion."""

    async def test_fake_implements_contract(self) -> None:
        from arvel.storage.fakes import StorageFake

        fake = StorageFake()
        assert isinstance(fake, StorageContract)

    async def test_fake_put_and_get(self) -> None:
        from arvel.storage.fakes import StorageFake

        fake = StorageFake()
        await fake.put("test.txt", b"content")
        data = await fake.get("test.txt")
        assert data == b"content"

    async def test_fake_assert_stored(self) -> None:
        from arvel.storage.fakes import StorageFake

        fake = StorageFake()
        await fake.put("uploaded.jpg", b"\xff\xd8")
        fake.assert_stored("uploaded.jpg")


class TestStoragePathSanitization:
    """FR-099/SEC-023/NFR-036: Directory traversal, absolute paths, null bytes rejected."""

    @pytest.mark.parametrize(
        "malicious_path,reason",
        [
            ("../../../etc/passwd", "contains .."),
            ("avatars/../../secret.txt", "contains .."),
            ("/etc/shadow", "absolute path"),
            ("file\x00evil.txt", "null byte"),
            ("", "empty path"),
        ],
    )
    def test_sanitize_rejects_malicious_path(self, malicious_path: str, reason: str) -> None:
        from arvel.storage.drivers.local_driver import _sanitize_path

        with pytest.raises(StoragePathError):
            _sanitize_path(malicious_path)

    @pytest.mark.parametrize(
        "malicious_path",
        [
            "../../../etc/passwd",
            "/etc/shadow",
            "file\x00evil.txt",
        ],
    )
    def test_sanitize_rejects_on_get_paths(self, malicious_path: str) -> None:
        from arvel.storage.drivers.local_driver import _sanitize_path

        with pytest.raises(StoragePathError):
            _sanitize_path(malicious_path)

    def test_storage_path_error_attributes(self) -> None:
        err = StoragePathError("../evil", "contains ..")
        assert err.path == "../evil"
        assert err.reason == "contains .."
        assert "../evil" in str(err)


class TestStorageConfig:
    """NFR-038: StorageSettings uses STORAGE_ env prefix. SEC: S3 secret is SecretStr."""

    def test_defaults(self, clean_env: None) -> None:
        from arvel.storage.config import StorageSettings

        settings = StorageSettings()
        assert settings.driver == "local"
        assert settings.local_root == ".tests/storage/app"

    def test_s3_secret_is_secret(self) -> None:
        from arvel.storage.config import StorageSettings

        settings = StorageSettings()
        assert hasattr(settings.s3_secret_key, "get_secret_value")
