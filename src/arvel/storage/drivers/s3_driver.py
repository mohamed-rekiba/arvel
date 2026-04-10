"""S3Storage — AWS S3 / S3-compatible object storage via aiobotocore."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from botocore.exceptions import ClientError

from arvel.storage.contracts import StorageContract
from arvel.support.utils import data_get

if TYPE_CHECKING:
    import builtins
    from datetime import timedelta


def _is_object_not_found(exc: BaseException) -> bool:
    if isinstance(exc, ClientError):
        code = data_get(exc.response, "Error.Code", "")
        return code in ("NoSuchKey", "404", "NotFound")
    return type(exc).__name__ == "NoSuchKey"


class S3Storage(StorageContract):
    """Storage backed by S3 or an S3-compatible API using an async aiobotocore client."""

    def __init__(
        self,
        client: Any,
        bucket: str,
        region: str = "us-east-1",
        endpoint_url: str = "",
    ) -> None:
        self._client = client
        self._bucket = bucket
        self._region = region
        self._endpoint_url = endpoint_url.rstrip("/") if endpoint_url else ""

    async def put(
        self,
        path: str,
        data: bytes,
        *,
        content_type: str | None = None,
    ) -> None:
        await self._client.put_object(
            Bucket=self._bucket,
            Key=path,
            Body=data,
            ContentType=content_type or "application/octet-stream",
        )

    async def get(self, path: str) -> bytes:
        try:
            response = await self._client.get_object(Bucket=self._bucket, Key=path)
        except Exception as exc:
            if _is_object_not_found(exc):
                raise FileNotFoundError(f"File not found: {path}") from exc
            raise
        body = response["Body"]
        return await body.read()

    async def delete(self, path: str) -> bool:
        await self._client.delete_object(Bucket=self._bucket, Key=path)
        return True

    async def exists(self, path: str) -> bool:
        try:
            await self._client.head_object(Bucket=self._bucket, Key=path)
        except Exception:
            return False
        return True

    async def url(self, path: str) -> str:
        if self._endpoint_url:
            return f"{self._endpoint_url}/{self._bucket}/{path}"
        return f"https://{self._bucket}.s3.{self._region}.amazonaws.com/{path}"

    async def temporary_url(self, path: str, expiration: timedelta) -> str:
        expires_in = int(expiration.total_seconds())
        return await self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": path},
            ExpiresIn=expires_in,
        )

    async def size(self, path: str) -> int:
        try:
            response = await self._client.head_object(Bucket=self._bucket, Key=path)
        except Exception as exc:
            if _is_object_not_found(exc):
                raise FileNotFoundError(f"File not found: {path}") from exc
            raise
        return int(response["ContentLength"])

    async def list(self, prefix: str = "") -> builtins.list[str]:
        response = await self._client.list_objects_v2(Bucket=self._bucket, Prefix=prefix)
        contents = response.get("Contents")
        if not contents:
            return []
        return [item["Key"] for item in contents if "Key" in item]
