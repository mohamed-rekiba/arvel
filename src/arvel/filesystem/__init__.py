"""arvel.filesystem — the Storage manager on **fsspec** (mandated engine; DR-0002).

``local`` is the core driver; ``s3``/``gcs``/``azure`` need their extras — all are real
fsspec filesystems (S3-compatible via ``endpoint_url`` + path-style, so AWS/RustFS/Ceph/R2/
Supabase all work). fsspec is sync, so blocking calls run in a worker thread (anyio)
to keep arvel async-first. fsspec is imported lazily. Grounded in knowledge/port/16-managers.md.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import mimetypes
from collections.abc import AsyncIterable, AsyncIterator
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any

import msgspec
from anyio.to_thread import run_sync

from arvel.kernel import Settings
from arvel.support.manager import Manager, MissingExtraError

if TYPE_CHECKING:
    from arvel.dates import Date

#: Default chunk size for :meth:`Filesystem.read_stream` — 1 MiB.
DEFAULT_CHUNK_SIZE = 1024 * 1024


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


class Visibility(Enum):
    """Public/private file visibility — a closed set, not a bare string."""

    PUBLIC = "public"
    PRIVATE = "private"


class UnknownDiskError(MissingExtraError):
    """A storage disk name isn't a configured disk and has no built-in driver of that name.

    Subclasses ``MissingExtraError`` (so existing ``except MissingExtraError`` handlers still catch
    it) but replaces its misleading "install arvel[<name>]" text with a message that names the
    configured disks — the common cause is a typo or an unconfigured disk, not a missing extra."""

    def __init__(self, name: str, known: str) -> None:
        RuntimeError.__init__(
            self,
            f"No storage disk {name!r} is configured (filesystems.disks: {known}) and no built-in "
            f"{name!r} driver exists. Add it under filesystems.disks, or fix the disk name.",
        )


class UnsupportedDriverOperation(RuntimeError):
    """Raised when a disk's driver doesn't support the requested operation (parity:
    ``temporaryUrl`` throws a ``RuntimeException`` on a driver without presigned-URL support)."""


class PathTraversalError(ValueError):
    """Raised when a path uses ``..`` to climb above the disk root (Flysystem parity)."""

    def __init__(self, path: str) -> None:
        super().__init__(f"path escapes the disk root: {path!r}")


class Filesystem:
    """disk API over an fsspec filesystem (async via worker threads)."""

    def __init__(
        self,
        fs: Any,
        root: str = "",
        *,
        url: str | None = None,
        endpoint_url: str | None = None,
        default_visibility: Visibility = Visibility.PUBLIC,
    ) -> None:
        self._fs = fs
        self._root = root.rstrip("/")
        self._url = url
        self._endpoint_url = endpoint_url
        self._default_visibility = default_visibility

    @property
    def fs(self) -> Any:
        return self._fs

    def _full(self, path: str) -> str:
        # Keys often derive from user input; a `..` segment must never escape the disk root
        # (Flysystem's PathTraversalDetected guard). Normalize, then reject any climb-out.
        segments: list[str] = []
        for segment in path.replace("\\", "/").split("/"):
            if segment in ("", "."):
                continue
            if segment == "..":
                if not segments:
                    raise PathTraversalError(path)
                segments.pop()
                continue
            segments.append(segment)
        relative = "/".join(segments)
        return f"{self._root}/{relative}" if self._root else relative

    def _protocol(self) -> tuple[str, ...]:
        proto = self._fs.protocol
        return (proto,) if isinstance(proto, str) else tuple(proto)

    def _is(self, *names: str) -> bool:
        return any(name in self._protocol() for name in names)

    def _relative(self, full_path: str) -> str:
        """The disk-root-relative form of an fsspec-returned absolute/full path."""
        full_path = full_path.lstrip("/")
        root = self._root.lstrip("/")
        if root and full_path.startswith(f"{root}/"):
            return full_path[len(root) + 1 :]
        if full_path == root:
            return ""
        return full_path

    def _parent(self, full_path: str) -> str:
        return full_path.rsplit("/", 1)[0] if "/" in full_path else ""

    # -- content ------------------------------------------------------------

    async def put(self, path: str, contents: bytes | str) -> str:
        data = contents.encode() if isinstance(contents, str) else contents
        full = self._full(path)

        def _write() -> None:
            parent = self._parent(full)
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

    async def append(self, path: str, data: bytes | str) -> str:
        """Append ``data`` to ``path`` (creating it if missing). Read-modify-write over the
        existing content — not atomic, so concurrent writers can race (documented)."""
        content = data.encode() if isinstance(data, str) else data
        existing = await self.get(path) if await self.exists(path) else b""
        return await self.put(path, existing + content)

    async def prepend(self, path: str, data: bytes | str) -> str:
        """Prepend ``data`` to ``path`` (creating it if missing). Same non-atomic
        read-modify-write caveat as :meth:`append`."""
        content = data.encode() if isinstance(data, str) else data
        existing = await self.get(path) if await self.exists(path) else b""
        return await self.put(path, content + existing)

    async def json(self, path: str) -> Any:
        """Read ``path`` and JSON-decode it."""
        return json.loads(await self.get(path))

    async def put_json(self, path: str, data: Any) -> str:
        """JSON-encode ``data`` and store it at ``path``; returns the stored path."""
        return await self.put(path, json.dumps(data))

    async def checksum(self, path: str, algo: str = "sha256") -> str:
        """Hex digest of ``path``'s content (``algo``: any name ``hashlib.new`` accepts) — streamed
        in chunks so a large file isn't loaded into memory all at once."""
        digest = hashlib.new(algo)
        async for chunk in self.read_stream(path):
            digest.update(chunk)
        return digest.hexdigest()

    async def put_file(self, directory: str, file: Any, name: str | None = None) -> str:
        """Store an ``UploadedFile``-like object (or raw ``bytes``/``str``) under ``directory``;
        returns the stored path. Without ``name``, a random collision-free name is generated
        (keeping the source's ``.extension`` when duck-typed off one — e.g. ``UploadedFile``)."""
        extension = ""
        if isinstance(file, bytes | str):
            contents: bytes | str = file
        else:
            contents = await file.read()
            # sanitize: a duck-typed .extension may be a raw client filename token containing `/`
            # or `.`, which would inject path segments into the key. Keep only [A-Za-z0-9].
            raw_ext = str(getattr(file, "extension", "") or "")
            extension = "".join(ch for ch in raw_ext if ch.isascii() and ch.isalnum())[:10]
        if name is None:
            from arvel.support import Str

            name = f"{Str.random(40)}.{extension}" if extension else Str.random(40)
        path = f"{directory.rstrip('/')}/{name}" if directory else name
        return await self.put(path, contents)

    # -- existence / metadata -------------------------------------------------

    async def exists(self, path: str) -> bool:
        return bool(await run_sync(self._fs.exists, self._full(path)))

    async def missing(self, path: str) -> bool:
        return not await self.exists(path)

    async def size(self, path: str) -> int:
        """The size in bytes of ``path``; raises ``FileNotFoundError`` if it doesn't exist."""
        full = self._full(path)
        info = await run_sync(self._fs.info, full)
        return int(info["size"])

    async def last_modified(self, path: str) -> Date:
        """The last-modified time of ``path`` as a :class:`arvel.dates.Date`; raises
        ``FileNotFoundError`` if it doesn't exist. Local fsspec reports epoch ``mtime``; s3
        reports an aware ``LastModified`` datetime — both are handled."""
        from arvel.dates import Date

        full = self._full(path)
        info = await run_sync(self._fs.info, full)
        raw = info.get("mtime", info.get("LastModified"))
        if isinstance(raw, datetime):
            stamp = raw
        elif isinstance(raw, int | float):
            stamp = datetime.fromtimestamp(float(raw), tz=UTC)
        else:
            stamp = datetime.fromisoformat(str(raw))
        return Date.from_py(stamp)

    async def mime_type(self, path: str) -> str:
        """The guessed MIME type of ``path`` from its extension (stdlib ``mimetypes``), falling
        back to ``application/octet-stream``. Pure string inspection — no I/O."""
        guessed, _ = mimetypes.guess_type(path)
        return guessed or "application/octet-stream"

    # -- copy / move ----------------------------------------------------------

    async def copy(self, src: str, dst: str) -> str:
        full_src, full_dst = self._full(src), self._full(dst)

        def _copy() -> None:
            parent = self._parent(full_dst)
            if parent:
                self._fs.makedirs(parent, exist_ok=True)
            self._fs.cp(full_src, full_dst)

        await run_sync(_copy)
        return full_dst

    async def move(self, src: str, dst: str) -> str:
        full_src, full_dst = self._full(src), self._full(dst)

        def _move() -> None:
            parent = self._parent(full_dst)
            if parent:
                self._fs.makedirs(parent, exist_ok=True)
            self._fs.mv(full_src, full_dst)

        await run_sync(_move)
        return full_dst

    async def delete(self, path: str) -> bool:
        full = self._full(path)

        def _delete() -> None:
            with contextlib.suppress(FileNotFoundError):  # idempotent: already-gone is success
                self._fs.rm(full)

        await run_sync(_delete)
        return True

    # -- directory listing ----------------------------------------------------

    async def files(self, directory: str = "") -> list[str]:
        """Non-recursive file listing under ``directory``, relative to the disk root."""
        full_dir = self._full(directory)

        def _list() -> list[str]:
            if not self._fs.exists(full_dir):
                return []
            entries = self._fs.ls(full_dir, detail=True)
            return sorted(self._relative(e["name"]) for e in entries if e.get("type") == "file")

        return await run_sync(_list)

    async def all_files(self, directory: str = "") -> list[str]:
        """Recursive file listing under ``directory``, relative to the disk root."""
        full_dir = self._full(directory)

        def _list() -> list[str]:
            if not self._fs.exists(full_dir):
                return []
            found = self._fs.find(full_dir, withdirs=False)
            return sorted(self._relative(p) for p in found)

        return await run_sync(_list)

    async def directories(self, directory: str = "") -> list[str]:
        """Non-recursive subdirectory listing under ``directory``, relative to the disk root."""
        full_dir = self._full(directory)

        def _list() -> list[str]:
            if not self._fs.exists(full_dir):
                return []
            entries = self._fs.ls(full_dir, detail=True)
            return sorted(
                self._relative(e["name"]) for e in entries if e.get("type") == "directory"
            )

        return await run_sync(_list)

    async def all_directories(self, directory: str = "") -> list[str]:
        """Recursive subdirectory listing under ``directory`` (excluding ``directory`` itself),
        relative to the disk root."""
        full_dir = self._full(directory)

        def _list() -> list[str]:
            if not self._fs.exists(full_dir):
                return []
            found = self._fs.find(full_dir, withdirs=True, detail=True)
            return sorted(
                relative
                for path, info in found.items()
                if info.get("type") == "directory" and (relative := self._relative(path))
            )

        return await run_sync(_list)

    async def make_directory(self, directory: str) -> bool:
        full = self._full(directory)
        await run_sync(lambda: self._fs.makedirs(full, exist_ok=True))
        return True

    async def delete_directory(self, directory: str) -> bool:
        full = self._full(directory)

        def _delete() -> None:
            if self._fs.exists(full):
                self._fs.rm(full, recursive=True)

        await run_sync(_delete)
        return True

    # -- streaming --------------------------------------------------------------

    async def read_stream(
        self, path: str, chunk_size: int = DEFAULT_CHUNK_SIZE
    ) -> AsyncIterator[bytes]:
        """Yield ``path`` in ``chunk_size`` chunks without loading the whole object into memory;
        each chunk read runs in a worker thread."""
        full = self._full(path)
        handle = await run_sync(lambda: self._fs.open(full, "rb"))
        try:
            while True:
                chunk = await run_sync(handle.read, chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            await run_sync(handle.close)

    async def write_stream(self, path: str, stream: AsyncIterable[bytes]) -> str:
        """Write an async byte stream to ``path`` (each chunk written in a worker thread);
        returns the stored path."""
        full = self._full(path)

        def _open() -> Any:
            parent = self._parent(full)
            if parent:
                self._fs.makedirs(parent, exist_ok=True)
            return self._fs.open(full, "wb")

        handle = await run_sync(_open)
        try:
            async for chunk in stream:
                await run_sync(handle.write, chunk)
        finally:
            await run_sync(handle.close)
        return full

    # -- visibility ---------------------------------------------------------

    async def set_visibility(self, path: str, visibility: Visibility) -> None:
        """Set ``path``'s visibility. ``local``: chmod 0o644/0o600. ``s3``: the ``public-read``/
        ``private`` canned ACL (via s3fs ``chmod``).

        ``gcs``/``azure`` expose no per-object ACL through fsspec, so this **raises**
        :class:`UnsupportedDriverOperation` there rather than silently doing nothing — code that
        believes it privatized an object must not be left with a false sense of security. Set
        visibility at the bucket/container level out-of-band for those backends."""
        full = self._full(path)

        def _set() -> None:
            if self._is("file", "local"):
                mode = 0o644 if visibility is Visibility.PUBLIC else 0o600
                self._fs.chmod(full, mode)
            elif self._is("s3", "s3a"):
                acl = "public-read" if visibility is Visibility.PUBLIC else "private"
                self._fs.chmod(full, acl)
            else:
                # never a silent no-op: a caller trusting set_visibility(PRIVATE) to take effect
                # must hear that it didn't (F-019), rather than believe an object is protected.
                raise UnsupportedDriverOperation(
                    f"set_visibility is not supported by the {self._protocol()!r} driver — "
                    f"configure visibility at the bucket/container level"
                )

        await run_sync(_set)

    async def get_visibility(self, path: str) -> Visibility:
        """Read back ``path``'s visibility. ``gcs``/``azure`` have no per-object ACL via fsspec, so
        this reports the disk's configured default rather than a real per-object read."""
        full = self._full(path)

        def _get() -> Visibility:
            if self._is("file", "local"):
                mode = self._fs.info(full)["mode"]
                return Visibility.PUBLIC if mode & 0o004 else Visibility.PRIVATE
            if self._is("s3", "s3a"):
                bucket, key, _version = self._fs.split_path(full)
                acl = self._fs.call_s3("get_object_acl", Bucket=bucket, Key=key)
                for grant in acl.get("Grants", []):
                    grantee = grant.get("Grantee", {})
                    if grantee.get("URI", "").endswith("/AllUsers"):
                        return Visibility.PUBLIC
                return Visibility.PRIVATE
            return self._default_visibility

        return await run_sync(_get)

    # -- URLs -----------------------------------------------------------------

    def url(self, path: str) -> str:
        """A public URL for ``path``. A configured ``url`` prefix always wins (-style
        override); otherwise ``s3`` builds the endpoint/bucket/key URL and other drivers return
        the full disk path as a best-effort identifier."""
        full = self._full(path)
        if self._url:
            return f"{self._url.rstrip('/')}/{path.lstrip('/')}"
        if self._is("s3", "s3a"):
            if self._endpoint_url:
                return f"{self._endpoint_url.rstrip('/')}/{full.lstrip('/')}"
            bucket, _sep, key = full.partition("/")
            return f"https://{bucket}.s3.amazonaws.com/{key}"
        return full

    async def temporary_url(self, path: str, expires_in: timedelta) -> str:
        """A time-boxed signed URL for ``path``: ``s3`` via presigning, ``gcs``/``azure`` via the
        backend's ``sign`` (a signed URL / SAS token). Other drivers (e.g. ``local``) raise
        :class:`UnsupportedDriverOperation`."""
        full = self._full(path)
        seconds = int(expires_in.total_seconds())

        def _sign() -> str:
            if self._is("s3", "s3a"):
                return str(self._fs.url(full, expires=seconds))
            if self._is("gcs", "gs", "az", "abfs", "abfss"):
                return str(self._fs.sign(full, expiration=seconds))
            raise UnsupportedDriverOperation(
                f"temporary_url is not supported by the {self._protocol()!r} driver"
            )

        return await run_sync(_sign)


class FilesystemManager(Manager):
    """Resolves storage disks (fsspec filesystems) by config; ``disk()`` aliases ``driver()``."""

    def default_driver(self) -> str:
        return self._settings(
            FilesystemSettings
        ).default  # auto-loads + validates config("filesystems")

    def _make(self, name: str) -> Any:
        # name → driver indirection: a disk names its backend via `driver`, so `disk("uploads")`
        # with `{"driver": "local"}` builds the local backend from the `uploads` config section —
        # not `create_uploads_driver` (which doesn't exist). Falls back to name==driver.
        if name in self._creators:  # extend()-registered custom driver
            return self._creators[name](self.app)
        disks = self._settings(FilesystemSettings).disks
        driver = disks[name].get("driver", name) if name in disks else name
        creator = getattr(self, f"create_{driver}_driver", None)
        if creator is None:
            if name not in disks:
                known = ", ".join(sorted(disks)) or "(none configured)"
                raise UnknownDiskError(name, known)  # clear "unknown disk", not "install extra"
            raise MissingExtraError(driver)  # the disk's declared driver needs its extra installed
        return creator(name)

    def disk(self, name: str | None = None) -> Filesystem:
        disk: Filesystem = self.driver(name)
        return disk

    def swap_disk(self, name: str, disk: Filesystem) -> Filesystem:
        """Replace a disk's cached instance (the ``Storage.fake`` seam — see ``arvel.testing``).
        Bypasses config-driven construction entirely, so the swap sticks until :meth:`forget`.

        Named ``swap_disk`` rather than ``swap``: the ``Storage`` facade's auto-generated stub
        (``make stubs``) mirrors every public method on this manager, and a bare ``swap`` here
        would collide with — and mismatch — ``Facade.swap(instance)``, the whole-root swap every
        facade already inherits."""
        self._drivers[name] = disk
        return disk

    def forget(self, name: str) -> None:
        """Drop a disk's cached instance so the next access reconstructs it from config — restores
        the real driver after :meth:`swap_disk`."""
        self._drivers.pop(name, None)

    def _disk_config(self, name: str) -> dict[str, Any]:
        return self._settings(FilesystemSettings).disks.get(name, {})

    def create_local_driver(self, disk: str = "local") -> Filesystem:
        config = self._disk_config(disk)
        return Filesystem(
            _fsspec().filesystem("file"),
            root=config.get("root", ""),
            url=config.get("url"),
        )

    def create_s3_driver(self, disk: str = "s3") -> Filesystem:
        config = self._disk_config(disk)
        client_kwargs = (
            {"endpoint_url": config["endpoint_url"]} if config.get("endpoint_url") else {}
        )
        fs = _fsspec().filesystem(
            "s3",
            key=config.get("key"),
            secret=config.get("secret"),
            client_kwargs=client_kwargs,
            # SigV4 presigned URLs — botocore's legacy default (SigV2 query auth) is rejected by
            # RustFS and other modern S3-compatible stores, breaking `temporary_url` outright.
            config_kwargs={"signature_version": "s3v4"},
        )
        return Filesystem(
            fs,
            root=config.get("bucket", ""),
            url=config.get("url"),
            endpoint_url=config.get("endpoint_url"),
        )

    def create_gcs_driver(self, disk: str = "gcs") -> Filesystem:
        config = self._disk_config(disk)
        fs = _fsspec().filesystem("gcs", token=config.get("token"))
        return Filesystem(
            fs,
            root=config.get("bucket", ""),
            url=config.get("url"),
            default_visibility=Visibility(config.get("visibility", "public")),
        )

    def create_azure_driver(self, disk: str = "azure") -> Filesystem:
        config = self._disk_config(disk)
        if config.get("connection_string"):  # full conn string (also how Azurite/emulators connect)
            fs = _fsspec().filesystem("az", connection_string=config["connection_string"])
        else:
            fs = _fsspec().filesystem(
                "az",
                account_name=config.get("account_name"),
                account_key=config.get("account_key"),
            )
        return Filesystem(
            fs,
            root=config.get("container", ""),
            url=config.get("url"),
            default_visibility=Visibility(config.get("visibility", "public")),
        )


__all__ = [
    "DEFAULT_CHUNK_SIZE",
    "Filesystem",
    "FilesystemManager",
    "FilesystemSettings",
    "PathTraversalError",
    "UnsupportedDriverOperation",
    "Visibility",
]
