# File Storage

<a name="introduction"></a>
## Introduction

Arvel provides a unified filesystem abstraction over local disks and cloud object stores. The same async API works whether files live on the local disk, S3, Google Cloud Storage, or Azure Blob Storage — swap the driver via configuration without touching your code.

<a name="configuration"></a>
## Configuration

Storage is configured through `StorageConfig` (the `STORAGE_*` environment variables). Set the default disk, then per-disk settings under their own prefixes (`STORAGE_LOCAL_`, `STORAGE_S3_`, `STORAGE_GCS_`, `STORAGE_AZURE_`):

```ini
STORAGE_DEFAULT=local
STORAGE_LOCAL_ROOT=storage/app
STORAGE_LOCAL_URL=/storage     # prefix for generated URLs; also the serve-route path
STORAGE_LOCAL_SERVE=true       # let the framework serve files from the local disk
```

`STORAGE_LOCAL_URL` is the prefix `disk.url()` puts in front of stored paths. Keep it relative
(`/storage`) and the browser resolves it against the current origin; set it absolute
(`https://cdn.example.com`) when a CDN or object store fronts the files.

<a name="drivers"></a>
### Drivers

| Driver | Backend | Status |
|---|---|---|
| `local` | Local filesystem | Fully supported |
| `memory` | In-process | For tests |
| `s3` | Amazon S3 | Requires the `s3` extra |
| `gcs` | Google Cloud Storage | Partial |
| `azure` | Azure Blob Storage | Partial |

> [!WARNING]
> The cloud drivers (`s3`, `gcs`, `azure`) are partially implemented. Verify the operations you need against the driver source before relying on them in production. `local` and `memory` are complete.

<a name="registering-the-provider"></a>
### Registering the Provider

Storage is **opt-in**. Add `StorageServiceProvider` to `bootstrap/providers.py` before using the `Storage` facade — otherwise it raises a not-bound error.

<a name="obtaining-disk-instances"></a>
## Obtaining Disk Instances

The `Storage` facade returns a disk. With no argument you get the default disk; pass a name for a specific one:

```python
from arvel.facades import Storage

disk = Storage.disk()          # default disk
s3 = Storage.disk("s3")        # named disk
```

Every disk implements the same async `StorageDisk` protocol. All I/O methods are coroutines (`url` and `temporary_url` are synchronous).

<a name="retrieving-files"></a>
## Retrieving Files

```python
contents = await disk.get("avatars/1.png")   # bytes
exists = await disk.exists("avatars/1.png")
```

<a name="storing-files"></a>
## Storing Files

`put` accepts `bytes`, `str`, or a binary file object:

```python
await disk.put("avatars/1.png", image_bytes)
await disk.put("notes/hello.txt", "plain text")
```

<a name="deleting-files"></a>
## Deleting Files

```python
await disk.delete("avatars/1.png")
```

<a name="file-urls"></a>
## File URLs

Get a public URL for a stored file, or a time-limited signed URL for private files:

```python
public = disk.url("avatars/1.png")
temporary = disk.temporary_url("private/report.pdf", expiry=300)   # seconds
```

`temporary_url` on the local disk signs the URL with HMAC-SHA256 keyed from `APP_KEY`, so it needs
`APP_KEY` set (run `arvel key:generate`). Cloud drivers use their SDK's native pre-signing.

<a name="serving-local-files"></a>
## Serving Local Files

The local driver mints URLs, but something has to answer them. When `STORAGE_LOCAL_SERVE` is on
(the default) and `STORAGE_LOCAL_URL` is a relative path, `StorageServiceProvider` registers a
route — `GET {STORAGE_LOCAL_URL}/{path}` — that serves files straight from the disk root. This is
the equivalent of Laravel's `'serve' => true`.

- **Public files** (`disk.url(...)`) are served directly.
- **Signed files** (`disk.temporary_url(...)`) carry `token` and `expires` query params. The route
  verifies the HMAC and the expiry; a tampered or expired link gets `403`.
- A missing file, or any path that tries to escape the root, gets `404` — never a read outside the
  root.

Turn it off (`STORAGE_LOCAL_SERVE=false`) or point `STORAGE_LOCAL_URL` at an absolute URL when a
CDN or object store serves the files instead — then no route is registered.

> [!NOTE]
> Per-file visibility (rejecting a private file requested without a signature) isn't implemented
> yet. Until then the route serves any file under the root when asked without a signature, which is
> fine for public media but means private data shouldn't live on a publicly served local disk.

<a name="listing-files"></a>
## Listing Files

```python
paths = await disk.list("avatars")    # paths under a directory
all_paths = await disk.list()         # everything on the disk
```

<a name="testing"></a>
## Testing

`Storage.fake()` swaps in an in-memory disk and adds path assertions, so tests never touch the real filesystem or a cloud account:

```python
with Storage.fake():
    await Storage.disk().put("avatars/1.png", b"...")
    Storage.assert_exists("avatars/1.png")
    Storage.assert_missing("avatars/2.png")
```
