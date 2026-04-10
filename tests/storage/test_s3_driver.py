"""Tests for S3Storage driver — FR-096, FR-094.

Mocks aiobotocore so tests run without a real S3/MinIO server.
"""

from __future__ import annotations

from datetime import timedelta
from importlib import util
from unittest.mock import AsyncMock

import pytest

from arvel.storage.contracts import StorageContract

_has_botocore = util.find_spec("botocore") is not None
_requires_s3 = pytest.mark.skipif(not _has_botocore, reason="aiobotocore/botocore not installed")


@_requires_s3
class TestS3StorageDriver:
    """FR-096: S3Storage implements StorageContract via aiobotocore."""

    def _make_driver(self):
        from arvel.storage.drivers.s3_driver import S3Storage

        mock_client = AsyncMock()
        return S3Storage(
            client=mock_client,
            bucket="test-bucket",
            region="us-east-1",
            endpoint_url="https://s3.amazonaws.com",
        ), mock_client

    def test_s3_implements_contract(self) -> None:
        from arvel.storage.drivers.s3_driver import S3Storage

        assert issubclass(S3Storage, StorageContract)

    async def test_put_uploads_object(self) -> None:
        storage, client = self._make_driver()
        await storage.put("docs/file.pdf", b"pdf-bytes", content_type="application/pdf")
        client.put_object.assert_awaited_once_with(
            Bucket="test-bucket",
            Key="docs/file.pdf",
            Body=b"pdf-bytes",
            ContentType="application/pdf",
        )

    async def test_put_without_content_type(self) -> None:
        storage, client = self._make_driver()
        await storage.put("file.bin", b"data")
        call_kwargs = client.put_object.call_args[1]
        assert call_kwargs["ContentType"] == "application/octet-stream"

    async def test_get_returns_body_bytes(self) -> None:
        storage, client = self._make_driver()
        body_mock = AsyncMock()
        body_mock.read.return_value = b"file-content"
        client.get_object.return_value = {"Body": body_mock}
        result = await storage.get("docs/file.pdf")
        assert result == b"file-content"
        client.get_object.assert_awaited_once_with(Bucket="test-bucket", Key="docs/file.pdf")

    async def test_get_raises_file_not_found(self) -> None:
        storage, client = self._make_driver()
        client.get_object.side_effect = client.exceptions.NoSuchKey = type(
            "NoSuchKey", (Exception,), {}
        )
        client.get_object.side_effect = client.exceptions.NoSuchKey("missing")
        with pytest.raises(FileNotFoundError):
            await storage.get("missing.txt")

    async def test_delete_returns_true(self) -> None:
        storage, client = self._make_driver()
        result = await storage.delete("docs/file.pdf")
        assert result is True
        client.delete_object.assert_awaited_once()

    async def test_exists_returns_true_when_found(self) -> None:
        storage, client = self._make_driver()
        client.head_object.return_value = {"ContentLength": 100}
        assert await storage.exists("file.txt") is True

    async def test_exists_returns_false_when_missing(self) -> None:
        storage, client = self._make_driver()
        client.head_object.side_effect = Exception("Not found")
        assert await storage.exists("missing.txt") is False

    async def test_url_returns_public_url(self) -> None:
        storage, _ = self._make_driver()
        url = await storage.url("avatars/user.jpg")
        assert "test-bucket" in url
        assert "avatars/user.jpg" in url

    async def test_temporary_url_returns_presigned(self) -> None:
        """FR-094: temporary_url returns a time-limited signed URL."""
        storage, client = self._make_driver()
        client.generate_presigned_url.return_value = "https://s3.example.com/signed?token=abc"
        url = await storage.temporary_url("file.pdf", timedelta(hours=1))
        assert "signed" in url or "token" in url
        client.generate_presigned_url.assert_awaited_once()

    async def test_size_returns_content_length(self) -> None:
        storage, client = self._make_driver()
        client.head_object.return_value = {"ContentLength": 12345}
        result = await storage.size("file.pdf")
        assert result == 12345

    async def test_list_returns_keys(self) -> None:
        storage, client = self._make_driver()
        client.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "docs/a.txt"},
                {"Key": "docs/b.txt"},
            ]
        }
        result = await storage.list("docs/")
        assert result == ["docs/a.txt", "docs/b.txt"]

    async def test_list_empty_prefix(self) -> None:
        storage, client = self._make_driver()
        client.list_objects_v2.return_value = {}
        result = await storage.list()
        assert result == []
