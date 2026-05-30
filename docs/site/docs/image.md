# Image Manipulation

`arvel-image` is Arvel's port of [Spatie Image v3](https://spatie.be/docs/image/v3/introduction). It gives you a fluent, type-safe `Image` class for resizing, cropping, fitting, formatting, and saving — backed by Pillow, with no shelling out and no other native dependencies.

`arvel-image` is a separate workspace package. Install it through the `image` extra:

```bash
uv add "arvel[image]"
```

The only runtime dependency is Pillow. We deliberately don't ship support for ImageMagick, GD, or ffmpeg — see ADR-080 for the rationale.

## Loading

`Image.load(...)` accepts a path, a `bytes` object, or any binary file-like object. The source is fully read and decoded eagerly, so you can close the source without losing pixels.

```python
from arvel_image import Image


img = Image.load("/uploads/avatar.png")
img = Image.load(b"...png bytes...")
with open("/uploads/avatar.png", "rb") as fh:
    img = Image.load(fh)
```

## Resize, fit, crop

```python
img.resize(width=800, height=600)              # exact box, may distort
img.fit("cover", 800, 600)                     # fill the box, crop overflow
img.fit("contain", 800, 600)                   # fit inside the box, preserve aspect
img.crop(left=100, top=50, width=400, height=300)
```

`fit("cover", ...)` is what most thumbnail use cases want — the output exactly fills the requested box and excess pixels are cropped away. `fit("contain", ...)` shrinks to fit and never enlarges past the source.

## Format and quality

```python
img.format("webp")              # change output container
img.quality(85)                 # 1..100, only honoured for JPEG and WebP
img.save("/out/avatar.webp")
```

Supported formats: `jpeg` / `jpg`, `png`, `webp`, `gif`. Asking for anything else raises `UnsupportedFormatError` — drop down to Pillow directly if you need TIFF or BMP.

When you save as JPEG and the source has an alpha channel (`RGBA`, `LA`, or palette-with-transparency), `arvel-image` automatically composites it over a white background. JPEG can't encode alpha, so the choice is "white background" or "lose colour data" — we pick the safer default.

## Optimize

`optimize()` strips embedded EXIF metadata and auto-rotates the image to its correct orientation:

```python
img.optimize()
```

Call it before saving or converting — it's a cheap in-place operation with no visible quality loss. Useful any time you're republishing user-uploaded files and don't want to leak GPS coordinates, device models, or timestamps.

## Chaining

Every operation returns `self`, so a typical thumbnail pipeline reads top-to-bottom:

```python
(
    Image.load(upload_path)
    .optimize()
    .fit("cover", 256, 256)
    .quality(85)
    .format("webp")
    .save(target_path)
)
```

## Saving and serializing

```python
img.save("/out/thumb.webp")             # writes to disk; format inferred from extension
img.save("/out/thumb.bin", image_format="png")
data: bytes = img.to_bytes()            # current format
data = img.to_bytes(image_format="png") # explicit override
```

`to_bytes(...)` is what you reach for when you're streaming the result back through HTTP without touching disk.

## Properties

```python
img.width    # int
img.height   # int
```

These reflect the *current* state of the image (post-resize/crop), not the source.

## Async usage

The whole class is synchronous because Pillow is. If you call it from inside a request handler or a queued job, wrap the work in a worker thread so you don't block the event loop:

```python
import asyncio


@Route.post("/avatars")
async def upload_avatar(form: AvatarUpload) -> dict:
    target = f"storage/avatars/{form.user_id}.webp"

    def _process() -> None:
        (
            Image.load(form.file.read())
            .optimize()
            .fit("cover", 256, 256)
            .format("webp")
            .save(target)
        )

    await asyncio.to_thread(_process)
    return {"url": target}
```

For batch jobs that fan out across many images, dispatch each one as a queue job and let the worker pool do the threading.

---

## Media library

`arvel-image` also ships a full Spatie [laravel-medialibrary](https://spatie.be/docs/laravel-medialibrary/v11/introduction) port — `Media` model, `HasMedia` mixin, file ingestion, collections, conversions, and a default path generator. ADR-081 covers the schema scope; ADR-082 covers the runtime.

### Setup

Publish and run the migration once per app:

```bash
arvel vendor:publish --tag=arvel-image
arvel migrate
```

Mix `HasMedia` into the host model. Both `HasMedia` and `HasMediaMixin` refer to the same class — use whichever name reads better in your project:

```python
from arvel.database import Model
from arvel_image import HasMedia, Conversion, MediaCollection  # or HasMediaMixin


class User(Model, HasMedia):
    __tablename__ = "users"

    def register_media_collections(self) -> None:
        (
            self.add_media_collection("avatar")
            .single_file()
            .with_conversions(
                Conversion("thumb").fit(96, 96).format("webp"),
                Conversion("card").fit(320, 320).format("webp"),
            )
        )
```

### Adding media

`add_media(...)` accepts a path, raw bytes, or any binary file-like object:

```python
user = await User.find(1)

await user.add_media("/uploads/photo.jpg").to_media_collection("avatar")
await user.add_media(file.read(), file_name=file.filename).to_media_collection("avatar")
await user.add_media(open_file_handle, file_name="photo.jpg").to_media_collection("avatar")
```

Each call writes the original to the configured disk, runs registered conversions through a worker thread (Pillow stays synchronous), and inserts a `Media` row. The row always has a `uuid` assigned — safe to use in public URLs immediately. `single_file()` collections atomically replace the previous media — both row and files.

**From a URL** — downloads and ingests in one call. Private and loopback addresses are blocked:

```python
media = await user.add_media_from_url(
    "https://example.com/photo.jpg"
).to_media_collection("gallery")
```

`httpx` must be installed (`pip install httpx`). Redirects are not followed — pass the final URL directly.

**From base64** — accepts a raw base64 string or a `data:<mime>;base64,...` data URI:

```python
media = await user.add_media_from_base64(
    data_uri_or_raw_b64, "photo.jpg"
).to_media_collection("gallery")
```

**From another storage disk** — reads via the Storage facade so disk-level access controls apply:

```python
media = await (
    await user.add_media_from_disk("originals/photo.jpg", disk="s3")
).to_media_collection("gallery")
```

Omit `disk=` to use the default disk.

**From a string or bytes payload** — useful when you generate content in memory and want to persist it without writing a temp file first:

```python
media = await (
    user.add_media_from_string(csv_text, file_name="export.csv")
    .to_media_collection("exports")
)

media = await (
    user.add_media_from_string(pdf_bytes, file_name="report.pdf")
    .using_file_name("q1-report.pdf")
    .to_media_collection("documents")
)
```

**Short form** — when the chain would be trivial, `attach_media` ingests and persists in one call:

```python
media = await user.attach_media("/uploads/photo.jpg", collection="avatar")
media = await user.attach_media(file.read(), file_name=file.filename, collection="avatar")
```

### FileAdder chain methods

`add_media(...)` returns a `FileAdder` you can configure before calling `to_media_collection(...)`:

```python
media = await (
    user.add_media(bytes_, file_name="report.pdf")
    .to_disk("secure")                        # store on a specific disk
    .with_custom_properties({"source": "api", "uploaded_by": user.id})
    .to_media_collection("documents")
)
```

| Method | Description |
|---|---|
| `.to_disk(name)` | Override the collection's disk for this ingestion only |
| `.with_custom_properties(dict)` | Merge key/values into the row's `custom_properties` JSON field |
| `.with_properties(dict)` | Alias for `with_custom_properties` |
| `.use_name(name)` | Override the human-readable name (defaults to the file stem) |
| `.using_file_name(name)` | Set the stored file name (applied after any sanitizer) |
| `.set_file_name(name)` | Alias for `using_file_name` |
| `.sanitizing_file_name(fn)` | Pass a `str → str` callback that transforms the file name before storage |

### Reading media

```python
items: list[Media] = await user.get_media("gallery")    # ordered by order_column
first: Media | None = await user.get_first_media("avatar")
last:  Media | None = await user.get_last_media("avatar")

if first is not None:
    avatar_url  = await first.get_url()               # original
    thumb_url   = await first.get_url("thumb")        # registered conversion
    full_url    = await first.get_full_url("thumb")   # absolute URL (prepends app.url if needed)
    download    = await first.get_temporary_url(3600) # signed, 1-hour expiry

    print(first.human_readable_size)               # e.g. "1.4 MB"
    print(first.has_generated_conversion("thumb")) # True once conversions have run
```

**Filtering** — pass a dict of custom property conditions or a callable predicate:

```python
# All gallery items where custom_properties["source"] == "api"
api_items = await user.get_media("gallery", filters={"source": "api"})

# Custom predicate
large = await user.get_media("gallery", filters=lambda m: (m.size or 0) > 5_000_000)
```

**Cross-collection** — use `"*"` to fetch all media for the model regardless of collection:

```python
all_media = await user.get_media("*")
```

**Convenience URL helpers** — return the URL directly, without fetching the `Media` row first:

```python
# Returns the URL of the first media item in the collection,
# or fallback if the collection is empty.
url = await user.get_media_url("avatar", fallback="/img/default-avatar.png")
url = await user.get_media_url("avatar", conversion="thumb", fallback="/img/default-thumb.png")

# Aliases
url = await user.get_first_media_url("avatar", fallback="/img/default-avatar.png")
url = await user.get_last_media_url("avatar", fallback="/img/default-avatar.png")
```

### Custom properties

Custom properties are persisted in a JSON column on the `Media` row and survive through copies and conversions:

```python
media = await (
    user.add_media(file_bytes, file_name="contract.pdf")
    .with_custom_properties({"signed_by": "alice", "department": "legal"})
    .to_media_collection("contracts")
)
```

**Typed helpers** — prefer these over raw dict access:

```python
# Check presence (dot notation supported for nested keys)
if media.has_custom_property("department"):
    dept = media.get_custom_property("department")          # "legal"

# Nested access with dot notation
meta = media.get_custom_property("audit.reviewed_by", default="unknown")

# Write (in-memory; call await media.save() to persist)
media.set_custom_property("reviewed_at", "2026-05-24")
media.forget_custom_property("signed_by")

await media.save()
```

`get_custom_property` returns `default` (default `None`) when the key is absent or any intermediate node in a dot-path isn't a dict. Both `set_custom_property` and `forget_custom_property` are in-memory only — call `await media.save()` when you're done batching changes.

**Direct dict access** (still works, useful for bulk reads):

```python
props: dict = media.custom_properties   # {"signed_by": "alice", "department": "legal"}
signed_by = props.get("signed_by")
```

### Conversions

```python
Conversion("thumb").fit(96, 96).format("webp").quality(85)
Conversion("hero").resize(1920, 1080).format("jpg")
Conversion("square").crop(500, 500)
```

`fit` preserves aspect ratio, `resize` forces an exact box, `crop` cuts to size. If a conversion fails, the ingestion is rolled back atomically — no orphaned row or original file is left on disk.

### Collections

Declare all your collections in `register_media_collections()`:

```python
def register_media_collections(self) -> None:
    # Basic collection with conversions
    (
        self.add_media_collection("gallery")
        .with_conversions(Conversion("thumb").fit(200, 200))
    )

    # One file at a time — new upload replaces the old one
    self.add_media_collection("avatar").single_file()

    # Only accept PDFs, up to 20 MB
    (
        self.add_media_collection("documents")
        .accept_mime_types(["application/pdf"])
        .max_file_size(20 * 1024 * 1024)
    )

    # Store originals on "uploads", conversions on "cdn"
    (
        self.add_media_collection("assets")
        .use_disk("uploads")
        .use_conversions_disk("cdn")
    )

    # Keep only the 5 most-recent files
    self.add_media_collection("logs").only_keep_latest(5)

    # Return a fallback URL when the collection is empty
    (
        self.add_media_collection("avatar")
        .single_file()
        .use_fallback_url("/img/default-avatar.png")
        .use_fallback_url("/img/default-thumb.png", conversion="thumb")
    )

    # Reject files that fail a custom predicate
    from arvel_image import FileInfo

    (
        self.add_media_collection("signed-docs")
        .accepts_file(lambda info: info.file_name.endswith(".pdf"))
    )
```

`accepts_file` receives a `FileInfo` object with `.file_name` and `.mime_type` attributes. Return `False` to reject the upload before any bytes hit disk.

`use_fallback_url` can be called multiple times — once without a conversion name (applies to the original) and once per conversion name you want to cover.

| Method | Description |
|---|---|
| `.with_conversions(*conversions)` | Register conversions to run on each ingestion |
| `.single_file()` | Replace on add — only ever one file in the collection |
| `.use_disk(name)` | Override the storage disk for originals |
| `.use_conversions_disk(name)` | Store conversion derivatives on a separate disk |
| `.accept_mime_types(list)` | Reject files whose MIME type isn't in the list |
| `.max_file_size(bytes)` | Reject files larger than this many bytes |
| `.only_keep_latest(n)` | Prune oldest rows after each add so at most `n` remain. Mutually exclusive with `single_file()`. |
| `.use_fallback_url(url, conversion=None)` | URL to return when the collection is empty (or the conversion hasn't been generated yet) |
| `.accepts_file(fn)` | `FileInfo → bool` predicate; return `False` to reject the upload |

Collections are per-class — two unrelated `HasMedia` subclasses cannot share collection state. Once a class declares any collection, requesting a name it didn't register raises `UnknownCollectionError`. Hosts that never override `register_media_collections()` keep Spatie's permissive default behavior.

### Ordering media

Every `Media` row carries an `order_column` integer. It's assigned automatically on ingestion (the new row gets the next available position in its collection), so `get_media()` returns items in insertion order out of the box.

To reorder items — for example after a drag-and-drop UI interaction — pass the IDs in the desired order to `set_new_order`:

```python
from arvel_image import Media

# gallery_ids: ordered list of Media IDs from the frontend
await Media.set_new_order([42, 17, 88, 3])

# Custom starting value (default is 1)
await Media.set_new_order([42, 17, 88], start_order=0)
```

Unknown IDs are silently skipped. The method updates all rows in a single session transaction.

### Moving and copying

Transfer a `Media` row — and its file — to a different host model or collection:

```python
# Copy: original stays where it is, new row + file created on target
new_media = await media.copy(other_user, collection="gallery")

# Move: row updated in place, no file copy (the file path changes logically
# but no bytes are moved on disk)
await media.move(other_user, collection="archive")
```

`copy()` assigns a fresh UUID to the new row. `move()` returns the same `Media` instance with updated `model_type`, `model_id`, and `collection_name`.

### Bulk regeneration

Re-run conversions for existing media — useful after you add or change a conversion definition:

```python
from arvel_image import MediaLibrary

lib = MediaLibrary()

# Regenerate everything
count = await lib.regenerate()

# Regenerate for one host
count = await lib.regenerate(host=user)

# Regenerate one collection across all hosts
count = await lib.regenerate(collection="gallery")

# Regenerate one collection on one host
count = await lib.regenerate(host=user, collection="gallery")
```

Returns the number of `Media` rows processed. Rows with missing originals or unresolvable collections are skipped silently.

### Lifecycle

```python
await user.clear_media_collection("avatar")  # row + files for this collection
await user.delete_media("avatar")            # alias — same effect, shorter name
await media.delete()                         # row + original + every recorded conversion
```

**Clear all except specific items** — keep a set of `Media` rows and delete everything else in the collection:

```python
# Keep only the IDs the user chose to retain
await user.clear_media_collection_except("gallery", keep_media_ids=[42, 88])
```

**Delete the host while preserving files** — useful when you remove a soft-deletable model but want its media files to remain on disk for archival:

```python
await user.delete_preserving_media()
```

This deletes only the `Media` rows (and the host row), not the physical files on disk.

`Media.delete()` is best-effort on the file side: an unreachable disk does not block the row delete.

### Path generator

By default the media library stores files as `{id}/{file_name}` (originals) and `{id}/conversions/{conversion}-{file_name}` (derivatives). This matches the Spatie v11 default and is safe for public URLs.

To use a custom layout, implement the `PathGenerator` protocol and register it before boot:

```python
from arvel_image.media.path_generator import PathGenerator, set_path_generator
from arvel_image.media.model import Media


class DatePathGenerator:
    """Store originals as YYYY/MM/{file_name}."""

    def path_for(self, media: Media) -> str:
        from datetime import datetime
        d = media.created_at or datetime.utcnow()
        return f"{d.year}/{d.month:02d}/{media.file_name}"

    def path_for_conversion(self, media: Media, conversion: str) -> str:
        from datetime import datetime
        d = media.created_at or datetime.utcnow()
        return f"{d.year}/{d.month:02d}/conversions/{conversion}-{media.file_name}"


# Call once during app bootstrap (e.g. in ImageServiceProvider.register)
set_path_generator(DatePathGenerator())
```

`PathGenerator` is a structural `Protocol` — no inheritance required. Any class with `path_for(media)` and `path_for_conversion(media, conversion)` signatures satisfies it. To reset to the default, pass `DefaultPathGenerator()`:

```python
from arvel_image.media.path_generator import DefaultPathGenerator, set_path_generator

set_path_generator(DefaultPathGenerator())
```

The active generator is read via `get_path_generator()`, which returns the custom instance if one was set and the default otherwise.

### Migrating an existing database

If you have an existing `media` table created before this version, run the `001_alter_media_model_id` migration to change the `model_id` column from `INTEGER` to `VARCHAR(36)`. This is required if you have host models with UUID primary keys:

```bash
arvel migrate
```

New installations create `model_id` as `VARCHAR(36)` directly — no manual step needed.

---

If you only need the stateless `Image` class, none of the media library applies — `from arvel_image import Image` continues to work in any Python program without the migration or the provider.

## See also

- [File Storage](filesystem.md) — where you keep the bytes after manipulating them
- ADR-080 — Pillow-only scope
- ADR-081 — `arvel-image` media-library scope (schema)
- ADR-082 — `arvel-image` media-library runtime (sync conversions, polymorphic discriminator, path scheme)
- ADR-108 — `model_id` VARCHAR(36) for UUID host PKs
- ADR-109 — SSRF guard design for `add_media_from_url`
