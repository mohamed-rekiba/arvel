"""ManagedS3Storage — S3 driver that manages aiobotocore clients per operation."""

from __future__ import annotations

import inspect
from importlib import import_module
from typing import TYPE_CHECKING, Any

from botocore.exceptions import ClientError

from arvel.storage.contracts import StorageContract

if TYPE_CHECKING:
    import builtins
    from datetime import timedelta


def _is_object_not_found(exc: BaseException) -> bool:
    if isinstance(exc, ClientError):
        code = str(exc.response.get("Error", {}).get("Code", ""))
        return code in {"NoSuchKey", "404", "NotFound"}
    return False


class ManagedS3Storage(StorageContract):
    """S3-backed storage with internally managed aiobotocore clients."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str = "us-east-1",
        endpoint_url: str = "",
        access_key: str = "",
        secret_key: str = "",
    ) -> None:
        if not bucket:
            raise ValueError("STORAGE_S3_BUCKET is required for STORAGE_DRIVER=s3")
        self._bucket = bucket
        self._region = region
        self._endpoint_url = endpoint_url or None
        self._access_key = access_key or None
        self._secret_key = secret_key or None

    def _client_args(self) -> dict[str, str]:
        kwargs: dict[str, str] = {"region_name": self._region}
        if self._endpoint_url:
            kwargs["endpoint_url"] = self._endpoint_url
        if self._access_key:
            kwargs["aws_access_key_id"] = self._access_key
        if self._secret_key:
            kwargs["aws_secret_access_key"] = self._secret_key
        return kwargs

    async def _with_client(self, operation: str, **kwargs: Any) -> Any:
        session_module = import_module("aiobotocore.session")
        get_session = session_module.get_session

        session = get_session()
        async with session.create_client("s3", **self._client_args()) as client:
            fn = getattr(client, operation)
            result = fn(**kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

    async def put(
        self,
        path: str,
        data: bytes,
        *,
        content_type: str | None = None,
    ) -> None:
        await self._with_client(
            "put_object",
            Bucket=self._bucket,
            Key=path,
            Body=data,
            ContentType=content_type or "application/octet-stream",
        )

    async def get(self, path: str) -> bytes:
        try:
            response = await self._with_client("get_object", Bucket=self._bucket, Key=path)
        except Exception as exc:
            if _is_object_not_found(exc):
                raise FileNotFoundError(f"File not found: {path}") from exc
            raise
        body = response["Body"]
        return await body.read()

    async def delete(self, path: str) -> bool:
        await self._with_client("delete_object", Bucket=self._bucket, Key=path)
        return True

    async def exists(self, path: str) -> bool:
        try:
            await self._with_client("head_object", Bucket=self._bucket, Key=path)
        except Exception:
            return False
        return True

    async def url(self, path: str) -> str:
        if self._endpoint_url:
            return f"{self._endpoint_url.rstrip('/')}/{self._bucket}/{path}"
        return f"https://{self._bucket}.s3.{self._region}.amazonaws.com/{path}"

    async def temporary_url(self, path: str, expiration: timedelta) -> str:
        expires_in = int(expiration.total_seconds())
        result = await self._with_client(
            "generate_presigned_url",
            ClientMethod="get_object",
            Params={"Bucket": self._bucket, "Key": path},
            ExpiresIn=expires_in,
        )
        return str(result)

    async def size(self, path: str) -> int:
        try:
            response = await self._with_client("head_object", Bucket=self._bucket, Key=path)
        except Exception as exc:
            if _is_object_not_found(exc):
                raise FileNotFoundError(f"File not found: {path}") from exc
            raise
        return int(response["ContentLength"])

    async def list(self, prefix: str = "") -> builtins.list[str]:
        response = await self._with_client(
            "list_objects_v2",
            Bucket=self._bucket,
            Prefix=prefix,
        )
        contents = response.get("Contents")
        if not contents:
            return []
        return [item["Key"] for item in contents if "Key" in item]
