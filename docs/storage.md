# Storage

Where a file *lives* shouldn't dictate how you *read and write* it — local disk in development, S3
in production, maybe GCS or Azure for one customer. arvel hides that behind a uniform **disk** API
built on [fsspec](https://filesystem-spec.readthedocs.io): the same calls — `put`, `get`, `exists`,
`delete` — work everywhere, and you swap the disk in config without touching your code.

This page covers the basic read/write API, configuring disks, and a worked upload example.

!!! note "Local is core; cloud disks need an extra"
    The `local` disk works out of the box. Cloud disks pull their fsspec driver: `arvel[s3]`
    (s3fs — also covers S3-compatible endpoints), `arvel[gcs]` (gcsfs), or `arvel[azure]` (adlfs).

## The basics

```python
from arvel import Storage

await Storage.put("invoices/2026-06.pdf", pdf_bytes)
data = await Storage.get("invoices/2026-06.pdf")     # -> bytes
exists = await Storage.exists("invoices/2026-06.pdf")
await Storage.delete("invoices/2026-06.pdf")
```

`put` accepts `bytes` or `str` (text is UTF-8 encoded) and returns the full stored path. Every
call is `async`; fsspec is synchronous, so arvel runs the blocking work in a worker thread to
keep the event loop responsive.

## Disks

A disk is a named filesystem from config. `Storage` proxies the default disk; pick another with
`disk()`:

```python
await Storage.disk("s3").put("avatars/ada.png", png_bytes)
await Storage.disk("local").get("cache/report.json")
```

| Driver | Backend | Extra |
|--------|---------|-------|
| `local` | the local filesystem | none |
| `s3` | any S3-compatible store (AWS, RustFS, R2, Supabase) | `[s3]` |
| `gcs` | Google Cloud Storage | `[gcs]` |
| `azure` | Azure Blob Storage | `[azure]` |

```python
# config/filesystems.py
FILESYSTEMS = {
    "default": "s3",
    "disks": {
        "local": {"root": "storage/app"},
        "s3": {
            "bucket": "acme-media",
            "key": env("AWS_KEY"),
            "secret": env("AWS_SECRET"),
            "endpoint_url": env("S3_ENDPOINT"),   # set for RustFS / R2 / Supabase
        },
        "gcs": {
            "bucket": "acme-media",
            "token": env("GOOGLE_APPLICATION_CREDENTIALS"),  # path to a service-account JSON
        },
        "azure": {
            "container": "media",
            "connection_string": env("AZURE_STORAGE_CONNECTION_STRING"),  # also how Azurite connects
        },
    },
}
```

The `endpoint_url` is what makes the `s3` driver work against **any** S3-compatible service —
AWS, RustFS, Cloudflare R2, Supabase Storage — not just AWS. The `azure` disk takes either a full
`connection_string` (the form real Azure and the Azurite emulator both use) or `account_name` +
`account_key`.

## Worked example: store an upload

`request.file("avatar")` returns an `UploadedFile` with a `.store()` that writes it to a disk
and returns the path — it generates a random, collision-free filename and keeps the original
extension:

```python
async def upload_avatar(request):
    file = await request.file("avatar")          # an UploadedFile (or None if absent)
    path = await file.store("avatars")           # → "avatars/<random>.png" on the default disk
    # await file.store("avatars", disk="s3")     # …or a specific disk
    # await file.store_as("avatars", f"{user.id}.png")   # …or your own name
    user.avatar_path = path
    await user.save()
    return {"path": path}
```

`UploadedFile` also exposes `.client_name`, `.extension`, `.content_type`, and `.read()`.

> **Gotcha — user-supplied names.** Prefer `store()` (random name). If you pass a name to
> `store_as()`, don't build it from raw user input — a `../` could escape the directory.

## Content & metadata helpers

Beyond `put`/`get`, a disk has the rest of the `Storage` surface — content helpers, copy/move,
metadata, directory listing, streaming, visibility, and URLs. Every method is `async`, and every
path is relative to the disk's configured `root`.

```python
await Storage.append("logs/today.txt", "new line\n")   # read-modify-write; not atomic
await Storage.prepend("logs/today.txt", "header\n")

path = await Storage.put_file("avatars", file_bytes)        # random name, keeps .extension
path = await Storage.put_file("avatars", file_bytes, name="ada.png")   # explicit name

await Storage.size("invoices/2026-06.pdf")            # -> int (bytes)
await Storage.last_modified("invoices/2026-06.pdf")   # -> Date (arvel.dates)
await Storage.mime_type("invoices/2026-06.pdf")        # -> "application/pdf" (falls back to
                                                        #    "application/octet-stream")
await Storage.missing("invoices/2026-06.pdf")          # -> bool (inverse of exists)
```

`size`/`last_modified` raise `FileNotFoundError` on a missing path — they never return `None`
silently. `put_file` accepts raw `bytes`/`str`, or anything shaped like arvel's `UploadedFile`
(anything with an async `.read()`; its `.extension`, if present, is kept in the generated name).

## Copy, move, and directories

```python
await Storage.copy("drafts/report.docx", "archive/report.docx")   # source stays
await Storage.move("drafts/report.docx", "archive/report.docx")   # source is removed

await Storage.files("invoices")           # non-recursive, relative to the disk root
await Storage.all_files("invoices")       # recursive
await Storage.directories("invoices")     # non-recursive subdirectories
await Storage.all_directories("invoices") # recursive subdirectories

await Storage.make_directory("invoices/2026")
await Storage.delete_directory("invoices/2026")   # recursive
```

Every listing method returns paths **relative to the disk root** — never the driver's absolute
form — so the same code works unchanged whether the disk is `local` or `s3`.

## Streaming large files

`read_stream`/`write_stream` move data in fixed-size chunks (1 MiB by default) instead of loading
the whole object into memory — each chunk read/write runs in a worker thread, same as every other
disk call:

```python
async for chunk in Storage.read_stream("exports/full.csv", chunk_size=1024 * 1024):
    await response.write(chunk)


async def upload_chunks():
    yield b"..."
    yield b"..."


await Storage.write_stream("uploads/big.bin", upload_chunks())
```

## Visibility

`Visibility` is a closed enum (`PUBLIC`/`PRIVATE`), not a bare string:

```python
from arvel.filesystem import Visibility

await Storage.set_visibility("avatars/ada.png", Visibility.PUBLIC)
current = await Storage.get_visibility("avatars/ada.png")   # -> Visibility.PUBLIC
```

Driver mapping:

| Driver | Mechanism |
|--------|-----------|
| `local` | file mode: `0o644` (public) / `0o600` (private) |
| `s3` | the `public-read`/`private` canned ACL (s3fs `chmod`) |
| `gcs`/`azure` | **best-effort.** Neither exposes a per-object ACL through fsspec — `set_visibility` is a documented no-op and `get_visibility` reports the disk's configured `visibility` default (`disks.<name>.visibility`, `"public"` unless set), not a live per-object read. |

!!! note "Not every S3-compatible store enforces canned ACLs"
    Canned-ACL enforcement varies by S3-compatible implementation — some accept `put_object_acl`
    without applying real anonymous-read semantics. `set_visibility`/`get_visibility` always make
    the standard S3 API calls (so they work against AWS, Ceph, and other ACL-honoring stores);
    whether an unauthenticated `url()` fetch actually 200s is a property of the *service*, not of
    arvel.

## URLs and temporary URLs

```python
Storage.url("avatars/ada.png")   # public URL — a configured `url` prefix always wins

await Storage.temporary_url("invoices/2026-06.pdf", timedelta(minutes=15))   # s3 only: a
                                                                              # presigned, time-boxed URL
```

`url()` resolution order: the disk's configured `url` (`disks.<name>.url`) always wins; otherwise
`s3` builds an endpoint/bucket/key URL, and other drivers return the full disk path as a
best-effort identifier. `temporary_url` presigns a time-boxed GET via s3fs and only works on the
`s3` driver — every other driver raises `UnsupportedDriverOperation` rather than hand back a URL it
can't actually sign.

## Testing: `Storage.fake`

`arvel.testing.fake_storage(disk)` swaps a disk for a fresh temp-dir local one, so tests never
touch a real bucket:

```python
from arvel.testing import fake_storage, restore_storage, reset_fakes

async def test_avatar_upload():
    fake = fake_storage("s3")           # swaps just the "s3" disk; others stay real
    await Storage.disk("s3").put("avatars/ada.png", png_bytes)

    await fake.assert_exists("avatars/ada.png")
    await fake.assert_count("avatars", 1)
    # await fake.assert_missing("avatars/other.png")

    restore_storage("s3")               # or call reset_fakes() in teardown — it restores
                                         # every faked disk (plus every faked facade)
```

`fake_storage` reaches into `FilesystemManager.swap_disk` rather than replacing the whole
`Storage` facade root: a fake usually targets one named disk while the rest of the app keeps
using real ones, which a whole-root swap can't express. `reset_fakes()` (typically called in test
teardown) restores every faked disk alongside the regular facade fakes (`Mail`, `Queue`, `Event`).

## Common mistakes & gotchas

- **Forgetting the extra.** The `local` driver needs nothing, but `s3`/`gcs`/`azure` need their
  `[s3]`/`[gcs]`/`[azure]` packages installed — without them the disk raises a clear
  `MissingExtraError` telling you which to add.
- **Leading slashes.** Paths are relative to the disk's `root`; a leading `/` is stripped, so
  `"/a/b"` and `"a/b"` resolve the same.
- **Calling Storage outside an `await`.** Every method is async — `await` it. A bare
  `Storage.get(...)` returns a coroutine, not bytes.
- **Assuming `s3` means AWS.** Point `endpoint_url` at any S3-compatible host; the driver
  uses path-style addressing so RustFS/R2/Supabase work unchanged.
- **`append`/`prepend` aren't atomic.** Both are a read-modify-write over the whole file — fine
  for logs written from one place, risky under concurrent writers.
- **`temporary_url` isn't universal.** Only the `s3` driver supports it; calling it on `local`/
  `gcs`/`azure` raises `UnsupportedDriverOperation` rather than hand back a URL it can't sign.

## How it works

`Storage` is a facade over a `FilesystemManager` (a driver manager). Each disk wraps an fsspec
filesystem in a `Filesystem` object that prefixes the configured `root` and runs every blocking
fsspec call (`open`, `exists`, `rm`) in a worker thread via `anyio`, so the async surface never
blocks the loop. fsspec and the cloud backends are imported lazily, so `import arvel` stays
light until you touch a disk.

## See also

- [Validation](validation.md) — `file`/`image`/`mimes` rules for uploads.
- [About arvel](about.md) — the engines behind each disk.
