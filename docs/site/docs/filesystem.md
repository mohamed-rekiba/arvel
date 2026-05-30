# File Storage

The `Storage` facade gives you a unified API for reading and writing files across local disk, cloud storage, and anything else with a backend driver. The same code reads from `local` in development and `s3` in production — only the configuration changes.

## Configuration

```env
STORAGE_DEFAULT=local

STORAGE_DISKS_LOCAL_DRIVER=local
STORAGE_DISKS_LOCAL_ROOT=storage/app

STORAGE_DISKS_PUBLIC_DRIVER=local
STORAGE_DISKS_PUBLIC_ROOT=storage/app/public
STORAGE_DISKS_PUBLIC_URL=https://example.com/storage

STORAGE_DISKS_S3_DRIVER=s3
STORAGE_DISKS_S3_KEY=...
STORAGE_DISKS_S3_SECRET=...
STORAGE_DISKS_S3_REGION=us-east-1
STORAGE_DISKS_S3_BUCKET=my-app-uploads

STORAGE_DISKS_AZURE_DRIVER=azure
STORAGE_DISKS_AZURE_ACCOUNT=...
STORAGE_DISKS_AZURE_KEY=...
STORAGE_DISKS_AZURE_CONTAINER=uploads
```

The default disk (`STORAGE_DEFAULT`) is what `Storage.put(...)` uses when you don't specify one. Cloud drivers require their respective extra:

```bash
uv add "arvel[s3]"
uv add "arvel[azure]"
```

## Basic operations

```python
from arvel.facades import Storage


await Storage.disk("local").put("reports/q1.pdf", pdf_bytes)
content = await Storage.disk("local").get("reports/q1.pdf")
exists = await Storage.disk("local").exists("reports/q1.pdf")
await Storage.disk("local").delete("reports/q1.pdf")
```

When you omit `disk(...)`, the default disk is used:

```python
await Storage.put("hello.txt", b"hello world")
```

## Writing different kinds of content

```python
# Bytes
await Storage.put("file.bin", b"\x00\x01\x02")

# UTF-8 strings (auto-encoded)
await Storage.put("file.txt", "hello")

# Streamed from a request
await Storage.put_file_as("avatars", request.file, "avatar.png")
```

## Reading

```python
content = await Storage.get("file.txt")          # → bytes
text = await Storage.get_text("file.txt")        # → str (UTF-8 decoded)

async for chunk in Storage.read_stream("video.mp4"):
    yield chunk                                   # streamed read
```

## Listing files

```python
files = await Storage.disk("local").files("avatars")
# → ["avatars/alice.png", "avatars/bob.jpg", ...]

directories = await Storage.disk("local").directories("uploads")
all_files = await Storage.disk("local").all_files("uploads")  # recursive
```

## Public URLs

For files that should be publicly accessible:

```python
url = await Storage.disk("public").url("avatars/alice.png")
# → "https://example.com/storage/avatars/alice.png"
```

The `local` driver builds the URL from `STORAGE_DISKS_PUBLIC_URL`. Cloud drivers return native URLs.

## Temporary signed URLs

For private files where you want to give the client time-limited access:

```python
url = await Storage.disk("s3").temporary_url(
    "reports/secret.pdf",
    expires_in=300,           # seconds
)
```

The `local` driver supports this too — it generates HMAC-signed URLs via the local-driver temp URL machinery (see ADR-028).

## S3-compatible providers

The `s3` driver speaks the AWS S3 wire protocol and works against any provider that honors it. Point `STORAGE_S3_ENDPOINT` at the provider's S3 endpoint, set credentials via `STORAGE_S3_KEY` and `STORAGE_S3_SECRET`, and the same application code runs everywhere.

### Configuration knobs

All seven knobs live under the `STORAGE_S3_` prefix:

| Env var | Purpose | Default |
|---|---|---|
| `STORAGE_S3_BUCKET` | Bucket name | (required) |
| `STORAGE_S3_KEY` | Access key | (empty — falls back to `AWS_ACCESS_KEY_ID`) |
| `STORAGE_S3_SECRET` | Secret key | (empty — falls back to `AWS_SECRET_ACCESS_KEY`) |
| `STORAGE_S3_REGION` | Region (provider-specific; `auto` for R2) | `us-east-1` |
| `STORAGE_S3_ENDPOINT` | Provider's S3 endpoint URL | (empty — uses AWS) |
| `STORAGE_S3_PUBLIC_URL` | Base URL for `url()` (CDN / custom domain) | (empty — derives from endpoint) |
| `STORAGE_S3_ADDRESSING_STYLE` | `path`, `virtual`, or `auto` | `auto` |
| `STORAGE_S3_SIGNATURE_VERSION` | Signing algorithm | `s3v4` |

`url()` priority is `public_url` → `endpoint` (path-style) → AWS hostname. `temporary_url()` works for all S3-compatible providers — it generates a SigV4 pre-signed URL locally and returns it without any network round-trip.

### MinIO (self-hosted)

MinIO is the typical self-hosted choice — useful in development, testing, and for on-prem deployments. It needs **path-style addressing** because most MinIO setups don't have wildcard DNS for `<bucket>.<host>`.

```env
STORAGE_DEFAULT=s3

STORAGE_S3_ENDPOINT=http://minio.internal:9000
STORAGE_S3_PUBLIC_URL=http://minio.internal:9000/uploads
STORAGE_S3_KEY=your-minio-access-key
STORAGE_S3_SECRET=your-minio-secret-key
STORAGE_S3_BUCKET=uploads
STORAGE_S3_REGION=us-east-1
STORAGE_S3_ADDRESSING_STYLE=path
```

Notes:

- HTTP is fine for in-cluster traffic; terminate TLS at your ingress.
- `STORAGE_S3_REGION` is required by the SigV4 signer but MinIO ignores its value — pick anything, `us-east-1` is conventional.
- The MinIO Console (the web UI) runs on a separate port (`9001`) and is not part of the S3 endpoint.

### Cloudflare R2

R2 has **no egress fees** and an S3-compatible API. The endpoint is account-scoped:

```env
STORAGE_DEFAULT=s3

STORAGE_S3_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com
STORAGE_S3_PUBLIC_URL=https://cdn.example.com
STORAGE_S3_KEY=your-r2-access-key
STORAGE_S3_SECRET=your-r2-secret-key
STORAGE_S3_BUCKET=uploads
STORAGE_S3_REGION=auto
STORAGE_S3_SIGNATURE_VERSION=s3v4
```

Notes:

- `STORAGE_S3_REGION=auto` — R2 is a single global namespace and requires `auto`.
- `STORAGE_S3_PUBLIC_URL` points at your **custom domain** bound to the bucket (configured in the R2 dashboard or via Cloudflare DNS). Without it, `Storage.url(...)` returns the API-endpoint path, which isn't a public-facing URL.
- Pre-signed URLs (`temporary_url`) work against R2 — including for buckets without a custom domain.
- Not every S3 feature is supported. Notable gaps as of 2026: object-level ACLs (use bucket-level policies), some lifecycle rule fields, and `SELECT Object Content`. The basic put/get/delete/list flow works as on AWS.

### Hetzner Object Storage

Hetzner exposes per-location endpoints (Falkenstein, Nuremberg, Helsinki, Ashburn, Singapore):

```env
STORAGE_DEFAULT=s3

STORAGE_S3_ENDPOINT=https://fsn1.your-objectstorage.com
STORAGE_S3_KEY=your-hetzner-access-key
STORAGE_S3_SECRET=your-hetzner-secret-key
STORAGE_S3_BUCKET=uploads
STORAGE_S3_REGION=fsn1
STORAGE_S3_ADDRESSING_STYLE=virtual
```

Notes:

- Replace `fsn1` with your location code (`nbg1`, `hel1`, `ash`, `sin`).
- Hetzner supports **virtual-hosted style** — DNS resolves `<bucket>.<location>.your-objectstorage.com`. Public URLs follow the same pattern, so `STORAGE_S3_PUBLIC_URL` is optional (the driver-built endpoint URL is publicly addressable).
- Buckets are publicly readable by default if you mark them so; otherwise use `temporary_url` for time-limited access.

### Generic S3-compatible

For any provider not listed above (Backblaze B2, DigitalOcean Spaces, Wasabi, Linode/Akamai, Scaleway, Tigris, …), the same three questions apply:

1. **What's the endpoint?** Look it up in the provider's docs. Set `STORAGE_S3_ENDPOINT`.
2. **Path or virtual-hosted style?** If the provider serves objects at `https://<bucket>.<host>/<key>` and has wildcard DNS, use `virtual`. If at `https://<host>/<bucket>/<key>`, use `path`. When unsure, start with `path` — it's the safer default.
3. **What goes in `url()`?** If the provider gives you a CDN or custom domain, point `STORAGE_S3_PUBLIC_URL` at it. Otherwise, `Storage.url(...)` builds it from the endpoint and bucket.

Common region values: AWS uses geo codes (`us-east-1`, `eu-west-2`), R2 needs `auto`, Hetzner needs the location code, MinIO accepts any value (use `us-east-1`).

If `temporary_url` doesn't work against a provider, the most common cause is mismatched `signature_version`. Almost everything now wants `s3v4`; a few legacy setups still need `s3`.

## File metadata

```python
size = await Storage.size("reports/q1.pdf")              # bytes
mtime = await Storage.last_modified("reports/q1.pdf")    # datetime
mime = await Storage.mime_type("reports/q1.pdf")
```

## Copying and moving

```python
await Storage.copy("source.pdf", "dest.pdf")
await Storage.move("old.pdf", "new.pdf")
```

Cross-disk:

```python
await Storage.disk("local").get("temp.pdf") \
    | await Storage.disk("s3").put("permanent.pdf", ...)
```

For cross-disk transfers, use the `copy_between` helper or pipe streams manually.

## Validating uploaded files

When accepting file uploads, validate the content type and size **before** persisting:

```python
@Route.post("/avatar")
async def upload(file: UploadFile) -> dict:
    if file.content_type not in {"image/png", "image/jpeg"}:
        raise HTTPException(415, "Only PNG and JPEG allowed.")
    if file.size > 5 * 1024 * 1024:
        raise HTTPException(413, "Max 5 MB.")
    await Storage.disk("public").put_file_as("avatars", file, f"{user.id}.{file.content_type.split('/')[1]}")
    return {"ok": True}
```

For deeper sanitization (image dimension limits, EXIF stripping, malware scanning), use a dedicated library — the framework doesn't ship that out of the box.

## Where to next?

- [Cache](cache.md) — for ephemeral data.
- [Mail](mail.md) — attaching files to email.
