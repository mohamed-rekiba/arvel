"""GCS storage driver (requires ``arvel[gcs]``)."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, BinaryIO

if TYPE_CHECKING:
    from arvel.config.storage_config import GcsConfig


class GcsDriver:
    """StorageDisk backed by Google Cloud Storage via ``google-cloud-storage``.

    Install: ``pip install "arvel[gcs]"``
    """

    def __init__(
        self,
        config: GcsConfig | None = None,
        bucket: str = "",
        prefix: str = "",
        **client_kwargs: Any,
    ) -> None:
        try:
            _gcs_lib = importlib.import_module("google.cloud.storage")
        except ImportError as exc:
            raise ImportError(
                "GcsDriver requires the 'gcs' extra. Install it with: pip install 'arvel[gcs]'"
            ) from exc
        _gcs: Any = _gcs_lib

        if config is not None:
            bucket = config.bucket

        # google-cloud-storage stubs are incomplete; Any is an explicit declaration
        # that the GCS client API is intentionally untyped at the static level.
        self._client: Any = _gcs.Client(**client_kwargs)
        self._bucket_name = bucket
        self._prefix = prefix

    def _blob_name(self, path: str) -> str:
        return f"{self._prefix}{path}" if self._prefix else path

    async def exists(self, path: str) -> bool:
        import anyio.to_thread

        bucket = self._client.bucket(self._bucket_name)
        blob = bucket.blob(self._blob_name(path))
        result: bool = await anyio.to_thread.run_sync(blob.exists)
        return result

    async def get(self, path: str) -> bytes:
        import anyio.to_thread

        bucket = self._client.bucket(self._bucket_name)
        blob = bucket.blob(self._blob_name(path))
        data: bytes = await anyio.to_thread.run_sync(blob.download_as_bytes)
        return data

    async def put(self, path: str, contents: bytes | str | BinaryIO) -> bool:
        import anyio.to_thread

        if isinstance(contents, str):
            raw: bytes = contents.encode()
        elif isinstance(contents, bytes):
            raw = contents
        else:
            raw = contents.read()
        bucket = self._client.bucket(self._bucket_name)
        blob = bucket.blob(self._blob_name(path))
        await anyio.to_thread.run_sync(lambda: blob.upload_from_string(raw))
        return True

    async def delete(self, path: str) -> bool:
        import anyio.to_thread

        bucket = self._client.bucket(self._bucket_name)
        blob = bucket.blob(self._blob_name(path))
        await anyio.to_thread.run_sync(blob.delete)
        return True

    async def list(self, directory: str = "") -> list[str]:
        import anyio.to_thread

        prefix = self._blob_name(directory.rstrip("/") + "/") if directory else (self._prefix or "")

        def _list() -> list[str]:
            blobs = list(self._client.list_blobs(self._bucket_name, prefix=prefix or None))
            return [b.name[len(self._prefix) :] if self._prefix else b.name for b in blobs]

        return await anyio.to_thread.run_sync(_list)

    def url(self, path: str) -> str:
        return f"https://storage.googleapis.com/{self._bucket_name}/{self._blob_name(path)}"

    def temporary_url(self, path: str, expiry: int) -> str:
        import datetime

        bucket = self._client.bucket(self._bucket_name)
        blob = bucket.blob(self._blob_name(path))
        url: str = blob.generate_signed_url(
            expiration=datetime.timedelta(seconds=expiry), method="GET"
        )
        return url


__all__ = ["GcsDriver"]
