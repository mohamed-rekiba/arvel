"""arvel.filesystem — the Storage manager on **fsspec** (mandated engine; DR-0002).

``local`` is the core driver; ``s3``/``gcs``/``azure`` need their extras — all are real
fsspec filesystems (S3-compatible via ``endpoint_url`` + path-style, so AWS/RustFS/Ceph/R2/
Supabase all work). fsspec is sync, so blocking calls run in a worker thread (anyio)
to keep arvel async-first. fsspec is imported lazily. Grounded in knowledge/port/16-managers.md.
"""

from __future__ import annotations

from typing import Any

import msgspec
from anyio.to_thread import run_sync

from arvel.kernel import Settings
from arvel.support.manager import Manager


def _no_disks() -> dict[str, dict[str, Any]]:
    return {}


class FilesystemSettings(Settings):
    """Typed, validated view over the ``filesystems`` config section (DR-0016).

    ``default`` is the active disk name; ``disks`` maps name → per-driver config and stays an open
    ``dict`` (driver-specific keys like ``root``/bucket/credentials pass through untouched).
    """

    __config_key__ = "filesystems"
    default: str = "local"
    disks: dict[str, dict[str, Any]] = msgspec.field(default_factory=_no_disks)


def _fsspec() -> Any:
    """fsspec ships no type stubs — funnel it through Any at this single boundary."""
    import fsspec

    return fsspec


class Filesystem:
    """Laravel-style disk API over an fsspec filesystem (async via worker threads)."""

    def __init__(self, fs: Any, root: str = "") -> None:
        self._fs = fs
        self._root = root.rstrip("/")

    @property
    def fs(self) -> Any:
        return self._fs

    def _full(self, path: str) -> str:
        path = path.lstrip("/")
        return f"{self._root}/{path}" if self._root else path

    async def put(self, path: str, contents: bytes | str) -> str:
        data = contents.encode() if isinstance(contents, str) else contents
        full = self._full(path)

        def _write() -> None:
            parent = full.rsplit("/", 1)[0] if "/" in full else ""
            if parent:
                self._fs.makedirs(parent, exist_ok=True)
            with self._fs.open(full, "wb") as handle:
                handle.write(data)

        await run_sync(_write)
        return full

    async def get(self, path: str) -> bytes:
        full = self._full(path)

        def _read() -> bytes:
            with self._fs.open(full, "rb") as handle:
                return bytes(handle.read())

        return await run_sync(_read)

    async def exists(self, path: str) -> bool:
        return bool(await run_sync(self._fs.exists, self._full(path)))

    async def delete(self, path: str) -> bool:
        await run_sync(self._fs.rm, self._full(path))
        return True


class FilesystemManager(Manager):
    """Resolves storage disks (fsspec filesystems) by config; ``disk()`` aliases ``driver()``."""

    def default_driver(self) -> str:
        return self._settings(
            FilesystemSettings
        ).default  # auto-loads + validates config("filesystems")

    def disk(self, name: str | None = None) -> Filesystem:
        disk: Filesystem = self.driver(name)
        return disk

    def _disk_config(self, name: str) -> dict[str, Any]:
        return self._settings(FilesystemSettings).disks.get(name, {})

    def create_local_driver(self) -> Filesystem:
        root = self._disk_config("local").get("root", "")
        return Filesystem(_fsspec().filesystem("file"), root=root)

    def create_s3_driver(self) -> Filesystem:
        config = self._disk_config("s3")
        client_kwargs = (
            {"endpoint_url": config["endpoint_url"]} if config.get("endpoint_url") else {}
        )
        fs = _fsspec().filesystem(
            "s3", key=config.get("key"), secret=config.get("secret"), client_kwargs=client_kwargs
        )
        return Filesystem(fs, root=config.get("bucket", ""))

    def create_gcs_driver(self) -> Filesystem:
        config = self._disk_config("gcs")
        fs = _fsspec().filesystem("gcs", token=config.get("token"))
        return Filesystem(fs, root=config.get("bucket", ""))

    def create_azure_driver(self) -> Filesystem:
        config = self._disk_config("azure")
        if config.get("connection_string"):  # full conn string (also how Azurite/emulators connect)
            fs = _fsspec().filesystem("az", connection_string=config["connection_string"])
        else:
            fs = _fsspec().filesystem(
                "az",
                account_name=config.get("account_name"),
                account_key=config.get("account_key"),
            )
        return Filesystem(fs, root=config.get("container", ""))


__all__ = ["Filesystem", "FilesystemManager", "FilesystemSettings"]
