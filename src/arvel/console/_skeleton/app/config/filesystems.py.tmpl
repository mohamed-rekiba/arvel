"""Filesystem config — storage disks (real fsspec filesystems).

`local` is the core driver (writes under the project). `s3` is any S3-compatible store (AWS, RustFS,
Ceph, R2, MinIO via `endpoint_url` + path-style) and needs the `[s3]` extra; `gcs`/`azure` likewise.
Use a disk via the `Storage` facade (`await Storage.put(...)` / `Storage.disk("s3")...`).
"""

from arvel import env

config = {
    "default": env("FILESYSTEM_DISK", "local"),
    "disks": {
        "local": {"driver": "local", "root": "storage/app"},
        "s3": {
            "driver": "s3",
            "key": env("AWS_ACCESS_KEY_ID", ""),
            "secret": env("AWS_SECRET_ACCESS_KEY", ""),
            "bucket": env("AWS_BUCKET", ""),
            "endpoint_url": env("AWS_ENDPOINT", ""),  # set for non-AWS S3 (RustFS/MinIO/R2)
        },
    },
}
