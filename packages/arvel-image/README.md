# arvel-image

<p>
<a href="https://pypi.org/project/arvel-image/">
    <img src="https://img.shields.io/pypi/v/arvel-image?color=%2334D058&label=pypi" alt="PyPI">
</a>
<img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License">
</p>

Image transforms and a polymorphic media library for [Arvel](https://arvel.dev) — Python ports of two
Spatie packages in one wheel:

- [spatie/image v3](https://spatie.be/docs/image/v3/introduction) — fluent, Pillow-backed transforms.
- [spatie/laravel-medialibrary v11](https://spatie.be/docs/laravel-medialibrary/v11/introduction) — a
  polymorphic `media` table that attaches files to any model.

> **Status**: Pre-alpha.

---

**Documentation**: <a href="https://arvel.dev/packages/image" target="_blank">https://arvel.dev/packages/image</a>

---

## Install

```bash
uv add arvel-image
# or: pip install arvel-image
```

For AVIF / HEIC support, add Pillow-HEIF:

```bash
uv add 'arvel-image[heif]'
```

## Image transforms

`Image` is a fluent, synchronous wrapper around Pillow — no external binaries, no shell calls.

```python
from arvel_image import Image

(
    Image.load("photo.jpg")
    .orient()                 # honour EXIF rotation
    .fit("cover", 800, 600)
    .format("webp")
    .quality(85)
    .save("photo.webp")
)

# Get bytes (useful inside a request handler)
thumbnail: bytes = (
    Image.load("avatar.jpg").fit("cover", 256, 256).format("png").to_bytes()
)
```

The chain is lazy — `load` and the pixel operations just record what to do, and nothing decodes
or transforms until a terminal runs. So in an async handler, reach for the `*_async` terminals;
they offload the whole pipeline (decode + transforms + encode) to a worker thread, keeping the
event loop free:

```python
from arvel_image import Image

data: bytes = await (
    Image.load(source).fit("cover", 256, 256).format("webp").to_bytes_async()
)

await Image.load(source).fit("cover", 256, 256).save_async("avatar.webp")
```

### Operations

| Method | Description |
|---|---|
| `Image.load(source)` | Load from a path, file-like object, or `bytes` |
| `.orient()` | Auto-rotate based on EXIF orientation |
| `.fit(mode, width, height)` | `"cover"` or `"contain"` |
| `.resize(width=…, height=…)` | Stretch to exact dimensions |
| `.crop(left=…, top=…, width=…, height=…)` | Crop to a fixed window |
| `.width(px)` / `.height(px)` | Single-axis resize, preserves aspect ratio |
| `.format(fmt)` | `"jpeg"`, `"png"`, `"webp"`, `"gif"` |
| `.quality(q)` | 1–100, applies to JPEG and WebP |
| `.background(color)` | Fill transparent areas (e.g. `"white"`, `"#fff"`) |
| `.optimize()` | Enable Pillow's optimizer pass |
| `.save(path)` | Write to disk |
| `.save_async(path)` | `await`able `.save()` — offloads to a thread |
| `.to_bytes()` | Return raw `bytes` |
| `.to_bytes_async()` | `await`able `.to_bytes()` — offloads to a thread |

## Media library

`HasMedia` gives any model a polymorphic media collection — upload, store, retrieve, and auto-convert
files attached to any row.

Register the provider in `bootstrap/providers.py` and run the migration:

```python
from arvel_image import ImageServiceProvider

providers = [
    # ...other providers...
    ImageServiceProvider,
]
```

```bash
arvel migrate
```

### Add `HasMedia` to a model

```python
from arvel.database import Model, Timestamps, id_, string
from arvel_image import HasMedia, MediaCollection, Conversion


class Post(Model, Timestamps, HasMedia):
    __tablename__ = "posts"

    id: int = id_()
    title: str = string(200)

    def register_media_collections(self) -> None:
        (
            MediaCollection("cover")
            .single_file(True)             # one cover image per post
            .with_conversions(
                Conversion("thumb").fit("cover", 400, 300).format("webp"),
                Conversion("og").fit("contain", 1200, 630).format("jpeg").quality(90),
            )
            .register_on(self)
        )
```

### Attach media

```python
post = await Post.find_or_fail(post_id)

# From a file path
await post.add_media("uploads/photo.jpg").to_media_collection("cover")

# From uploaded bytes
await post.add_media(file_bytes, file_name="cover.jpg").to_media_collection("cover")

# From a URL (SSRF-guarded)
await post.add_media_from_url("https://example.com/image.jpg").to_media_collection("cover")

# From a base64 data URI
await post.add_media_from_base64(data_uri, file_name="cover.jpg").to_media_collection("cover")
```

### Retrieve media

```python
media_list = await post.get_media("cover")                          # all, ordered
url = await post.get_media_url("cover")                             # original
thumb_url = await post.get_media_url("cover", conversion="thumb")   # derived
first = await post.get_first_media("cover")
await post.clear_media_collection("cover")
```

### Conversions

Conversions are declarative chains. They run in a background job
(`GenerateImageConversionsJob`) dispatched automatically after each `add_media` call — no manual
wiring:

```python
from arvel_image.media.conversion import Conversion

Conversion("thumb").fit("cover", 400, 300).format("webp").quality(80)
Conversion("og").fit("contain", 1200, 630).format("jpeg").quality(90)
Conversion("avatar").resize(width=128, height=128).format("png")
```

### Collection options

`MediaCollection` is a fluent builder:

```python
(
    MediaCollection("gallery")
    .single_file(False)                          # keep all files (default)
    .only_keep_latest(10)                        # prune oldest beyond 10
    .accept_mime_types(["image/jpeg", "image/png"])
    .max_file_size(5 * 1024 * 1024)              # 5 MB limit
    .use_disk("s3")                              # separate disk for originals
    .use_conversions_disk("s3-public")           # separate disk for derivatives
    .use_fallback_url("/images/placeholder.jpg")
    .register_on(self)
)
```

## Why one package?

Laravel apps that use `spatie/image` almost always use `spatie/laravel-medialibrary` too. Shipping
both in one wheel means one extras flag (`arvel[image]`), one `arvel migrate`, and one provider to
register. The transform API (`Image`) is standalone — you can use it without the media library.

## License

MIT — see [LICENSE](../../LICENSE).
