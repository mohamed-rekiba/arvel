"""Azure Blob Storage driver (requires ``arvel[azure]``)."""

from __future__ import annotations

import importlib
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, BinaryIO, Protocol, Self, cast

if TYPE_CHECKING:
    from arvel.config.storage_config import AzureConfig


class _BlobClient(Protocol):
    """Async context manager wrapping a single Azure blob."""

    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, *args: object) -> None: ...
    async def exists(self) -> bool: ...
    async def download_blob(self) -> _DownloadStream: ...
    async def upload_blob(self, data: bytes, *, overwrite: bool = ...) -> Any: ...
    async def delete_blob(self) -> None: ...


class _DownloadStream(Protocol):
    async def readall(self) -> bytes: ...


class _BlobItem(Protocol):
    name: str


class _ContainerClient(Protocol):
    """Async context manager wrapping an Azure container."""

    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, *args: object) -> None: ...

    def list_blobs(self, *, name_starts_with: str | None = ...) -> AsyncIterator[_BlobItem]: ...


class _BlobServiceClientProto(Protocol):
    """Minimal interface of azure.storage.blob.aio.BlobServiceClient."""

    url: str

    def get_blob_client(self, container: str, blob: str) -> _BlobClient: ...

    def get_container_client(self, container: str) -> _ContainerClient: ...

    @classmethod
    def from_connection_string(cls, conn_str: str, **kwargs: Any) -> _BlobServiceClientProto: ...


class AzureDriver:
    """StorageDisk backed by Azure Blob Storage via ``azure-storage-blob``.

    Install: ``pip install "arvel[azure]"``
    """

    def __init__(
        self,
        config: AzureConfig | None = None,
        container: str = "",
        connection_string: str | None = None,
        account_url: str | None = None,
        prefix: str = "",
        account: str = "",
        account_key: str = "",
        **kwargs: Any,
    ) -> None:
        try:
            _azure_mod = importlib.import_module("azure.storage.blob.aio")
        except ImportError as exc:
            raise ImportError(
                "AzureDriver requires the 'azure' extra. "
                "Install it with: pip install 'arvel[azure]'"
            ) from exc

        if config is not None:
            container = config.container
            account = config.account
            account_key = config.key.get_secret_value()
            account_url = f"https://{config.account}.blob.core.windows.net"

        # Kept for SAS generation in temporary_url(); empty when only a public
        # account_url was supplied (no shared key available to sign with).
        self._account = account
        self._account_key = account_key

        # Use getattr to keep the constructor as Any; cast per-branch to the Protocol.
        _blob_svc_cls = _azure_mod.BlobServiceClient
        if connection_string:
            _cls: type[_BlobServiceClientProto] = cast(
                "type[_BlobServiceClientProto]", _blob_svc_cls
            )
            self._service: _BlobServiceClientProto = _cls.from_connection_string(
                connection_string, **kwargs
            )
        elif account_url:
            self._service = cast(
                "_BlobServiceClientProto",
                _blob_svc_cls(account_url=account_url, **kwargs),
            )
        else:
            raise ValueError("Provide either connection_string or account_url for AzureDriver")

        self._container = container
        self._prefix = prefix

    def _blob_name(self, path: str) -> str:
        return f"{self._prefix}{path}" if self._prefix else path

    async def exists(self, path: str) -> bool:
        async with self._service.get_blob_client(self._container, self._blob_name(path)) as blob:
            result: bool = await blob.exists()
            return result

    async def get(self, path: str) -> bytes:
        async with self._service.get_blob_client(self._container, self._blob_name(path)) as blob:
            stream = await blob.download_blob()
            return await stream.readall()

    async def put(self, path: str, contents: bytes | str | BinaryIO) -> bool:
        if isinstance(contents, str):
            data: bytes = contents.encode()
        elif isinstance(contents, bytes):
            data = contents
        else:
            data = contents.read()
        async with self._service.get_blob_client(self._container, self._blob_name(path)) as blob:
            await blob.upload_blob(data, overwrite=True)
        return True

    async def delete(self, path: str) -> bool:
        async with self._service.get_blob_client(self._container, self._blob_name(path)) as blob:
            await blob.delete_blob()
        return True

    async def list(self, directory: str = "") -> list[str]:
        prefix = (
            self._blob_name(directory.rstrip("/") + "/") if directory else (self._prefix or None)
        )
        async with self._service.get_container_client(self._container) as container:
            return [
                b.name[len(self._prefix) :] if self._prefix else b.name
                async for b in container.list_blobs(name_starts_with=prefix)
            ]

    def url(self, path: str) -> str:
        account_url = str(self._service.url)
        return f"{account_url.rstrip('/')}/{self._container}/{self._blob_name(path)}"

    def temporary_url(self, path: str, expiry: int) -> str:
        """Return a read-only URL with a SAS token that expires after *expiry* seconds.

        Requires a shared account key (``STORAGE_AZURE_KEY``); signing is a local
        crypto op, so this stays synchronous like the S3/GCS equivalents.
        """
        import datetime

        if not self._account or not self._account_key:
            raise ValueError(
                "AzureDriver.temporary_url requires an account name and key "
                "(set STORAGE_AZURE_ACCOUNT and STORAGE_AZURE_KEY)"
            )

        # azure-storage-blob ships no complete stubs; Any at this boundary mirrors
        # the aio client handling above.
        _blob: Any = importlib.import_module("azure.storage.blob")
        sas: str = _blob.generate_blob_sas(
            account_name=self._account,
            container_name=self._container,
            blob_name=self._blob_name(path),
            account_key=self._account_key,
            permission=_blob.BlobSasPermissions(read=True),
            expiry=datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=expiry),
        )
        return f"{self.url(path)}?{sas}"


__all__ = ["AzureDriver"]
