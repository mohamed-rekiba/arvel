"""S3 storage driver (requires ``arvel[s3]``).

Speaks the AWS S3 wire protocol and works against any S3-compatible
provider — AWS S3, MinIO, Cloudflare R2, Hetzner Object Storage,
Backblaze B2, DigitalOcean Spaces, Wasabi, and others. Provider-specific
configuration is documented in ``docs/site/docs/filesystem.md``.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, BinaryIO

if TYPE_CHECKING:
    from arvel.config.storage_config import S3Config


class S3Driver:
    """StorageDisk backed by S3 (or any S3-compatible provider) via ``aioboto3``.

    Install: ``pip install "arvel[s3]"``
    """

    def __init__(self, config: S3Config, *, prefix: str = "", **kwargs: Any) -> None:
        try:
            _aioboto3_lib = importlib.import_module("aioboto3")
            _boto3_lib = importlib.import_module("boto3")
        except ImportError as exc:
            raise ImportError(
                "S3Driver requires the 's3' extra. Install it with: pip install 'arvel[s3]'"
            ) from exc

        # aioboto3 and boto3 ship no complete type stubs; Any is an explicit
        # declaration that the session and its async-context-manager clients
        # are intentionally untyped at this boundary.
        self._aioboto3: Any = _aioboto3_lib
        self._boto3: Any = _boto3_lib
        self._config = config
        self._prefix = prefix
        self._session: Any = self._aioboto3.Session()
        self._extra_kwargs = kwargs

    def _key(self, path: str) -> str:
        return f"{self._prefix}{path}" if self._prefix else path

    def _client_kwargs(self) -> dict[str, Any]:
        # Lazy-import botocore so the import error message in __init__ stays
        # the source of truth for "extra not installed".
        botocore_config: Any = importlib.import_module("botocore.config")
        boto_config: Any = botocore_config.Config(
            signature_version=self._config.signature_version,
            s3={"addressing_style": self._config.addressing_style},
        )
        kwargs: dict[str, Any] = {
            "region_name": self._config.region,
            "config": boto_config,
        }
        if self._config.endpoint:
            kwargs["endpoint_url"] = self._config.endpoint
        access_key = self._config.key.get_secret_value()
        if access_key:
            kwargs["aws_access_key_id"] = access_key
            kwargs["aws_secret_access_key"] = self._config.secret.get_secret_value()
        return {**kwargs, **self._extra_kwargs}

    async def exists(self, path: str) -> bool:
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            try:
                await s3.head_object(Bucket=self._config.bucket, Key=self._key(path))
                return True  # noqa: TRY300
            except Exception:  # noqa: BLE001
                return False

    async def get(self, path: str) -> bytes:
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            resp = await s3.get_object(Bucket=self._config.bucket, Key=self._key(path))
            data: bytes = await resp["Body"].read()
            return data

    async def put(self, path: str, contents: bytes | str | BinaryIO) -> bool:
        if isinstance(contents, str):
            data: bytes = contents.encode()
        elif isinstance(contents, bytes):
            data = contents
        else:
            data = contents.read()
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            await s3.put_object(Bucket=self._config.bucket, Key=self._key(path), Body=data)
        return True

    async def delete(self, path: str) -> bool:
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            await s3.delete_object(Bucket=self._config.bucket, Key=self._key(path))
        return True

    async def list(self, directory: str = "") -> list[str]:
        prefix = self._key(directory.rstrip("/") + "/") if directory else (self._prefix or "")
        keys: list[str] = []
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            paginator = s3.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=self._config.bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    key: str = obj["Key"]
                    keys.append(key[len(self._prefix) :] if self._prefix else key)
        return keys

    def url(self, path: str) -> str:
        """Return the public URL for *path*.

        Priority: ``public_url`` (CDN / custom domain) → ``endpoint``
        (path-style — the safe default for self-hosted / non-DNS setups)
        → AWS hostname pattern.
        """
        key = self._key(path)
        if self._config.public_url:
            return f"{self._config.public_url.rstrip('/')}/{key}"
        if self._config.endpoint:
            return f"{self._config.endpoint.rstrip('/')}/{self._config.bucket}/{key}"
        return f"https://{self._config.bucket}.s3.{self._config.region}.amazonaws.com/{key}"

    def temporary_url(self, path: str, expiry: int) -> str:
        """Return a pre-signed GET URL that expires after *expiry* seconds.

        Uses the synchronous ``boto3`` client because ``generate_presigned_url``
        is a local cryptographic operation with no network I/O — running it
        inside an async context-managed ``aioboto3`` client would be wasteful.
        """
        client: Any = self._boto3.client("s3", **self._client_kwargs())
        url: str = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._config.bucket, "Key": self._key(path)},
            ExpiresIn=expiry,
        )
        return url


__all__ = ["S3Driver"]
