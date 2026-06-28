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

## How it works

`Storage` is a facade over a `FilesystemManager` (a driver manager). Each disk wraps an fsspec
filesystem in a `Filesystem` object that prefixes the configured `root` and runs every blocking
fsspec call (`open`, `exists`, `rm`) in a worker thread via `anyio`, so the async surface never
blocks the loop. fsspec and the cloud backends are imported lazily, so `import arvel` stays
light until you touch a disk.

## See also

- [Validation](validation.md) — `file`/`image`/`mimes` rules for uploads.
- [About arvel](about.md) — the engines behind each disk.
