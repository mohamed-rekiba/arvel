"""Filesystem configuration — MinIO is the kit's S3-compatible object store.

Sister file to ``cache.py`` / ``queue.py`` / ``database.py`` etc. The framework
reads storage settings from ``STORAGE_*`` environment variables via
:class:`arvel.config.storage_config.StorageConfig` (and friends) — see the env
vars in ``compose.yml`` and ``.env.example``. This module mirrors those
knobs as a single inventory point so the available disks are discoverable
in code and accessible via ``lookup("filesystems.disks.s3.bucket")``.

Wire path:

- ``STORAGE_DEFAULT`` → :attr:`default`
- ``STORAGE_S3_ENDPOINT`` → boto3 endpoint (in-network)
- ``STORAGE_S3_PUBLIC_URL`` → URL emitted in API responses; the
                                          dev stack proxies ``/media/*``
                                          through Caddy to MinIO so the
                                          browser stays on a single origin
                                          and the URL prefix matches
                                          ``STORAGE_LOCAL_URL=/media`` for
                                          a single SPA-side shape.
- ``STORAGE_S3_BUCKET`` → bucket name
- ``STORAGE_S3_KEY`` / ``STORAGE_S3_SECRET`` → MinIO credentials
- ``STORAGE_S3_ADDRESSING_STYLE`` → ``path`` for MinIO
"""

from __future__ import annotations

from arvel.support.env import env

# s3 is the kit's default because the compose stack bundles MinIO + Caddy and
# the SPA's "primary entry" Caddy edge (:8002) only serves /media/* correctly
# when the driver is s3 (Caddy proxies to MinIO). local mode is the opt-in
# zero-deps fallback — when local, the SPA must load from :8001 directly
# because the backend's serve=true route owns /media/* there, not Caddy.
default: str = env("STORAGE_DEFAULT", "s3")

disks: dict[str, dict[str, object]] = {
    "s3": {
        "driver": "s3",
        "endpoint": env("STORAGE_S3_ENDPOINT", "http://minio:9000"),
        "public_url": env("STORAGE_S3_PUBLIC_URL", "http://localhost:8002/media"),
        "bucket": env("STORAGE_S3_BUCKET", "arvel-ecommerce-kit"),
        "key": env("STORAGE_S3_KEY", "minioadmin"),
        "secret": env("STORAGE_S3_SECRET", "minioadmin"),
        "region": env("STORAGE_S3_REGION", "us-east-1"),
        "addressing_style": env("STORAGE_S3_ADDRESSING_STYLE", "path"),
    },
    "local": {
        "driver": "local",
        "root": env("STORAGE_LOCAL_ROOT", "storage/app"),
        "url": env("STORAGE_LOCAL_URL", ""),
    },
}
