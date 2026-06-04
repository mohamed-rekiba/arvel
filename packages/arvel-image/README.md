# arvel-image

<p>
<a href="https://pypi.org/project/arvel-image/">
    <img src="https://img.shields.io/pypi/v/arvel-image?color=%2334D058" alt="PyPI">
</a>
<img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License">
</p>

Image transforms and a polymorphic media library for [Arvel](https://arvel.dev), in one wheel.

- **`Image`** — fluent, Pillow-backed transforms. Resize, crop, fit, format, quality, optimize.
- **`HasMedia`** — attach files (any kind, not just images) to any model. One class attribute, one
  upload call, eager-loaded reads, automatic JSON serialization.

> **Status**: Pre-alpha.

---

**Documentation**: <a href="https://arvel.dev/packages/image" target="_blank">https://arvel.dev/packages/image</a>

---

## Install

```bash
uv add arvel-image
# or: pip install arvel-image
```

For AVIF / HEIC support:

```bash
uv add 'arvel-image[heif]'
```

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

---

## Quick start — attach an image to a model

The 30-second version. Three things to write, everything else is automatic.

```python
from arvel.database import Model, Timestamps, id_, string
from arvel_image import HasMedia


class Product(HasMedia, Model, Timestamps):
    __tablename__ = "products"
    __media_collection__ = "images"   # one string, that's the whole config

    id: int = id_()
    name: str = string(200)


# write
product = await Product.create(name="Sneakers")
await product.add_image(file_bytes, file_name="hero.jpg")
await product.add_image("https://cdn.example.com/photo.png")
await product.add_image("/tmp/upload.webp")

# read
product = await Product.with_("media").first()
print(product.first_media.url())          # original
print(product.image_url("thumbnail"))     # named conversion, with sensible fallbacks
for m in product.get_media():
    print(m.url(), m.srcset())

# serialize — to_dict() includes serialized media automatically
return product.to_dict()
# {
#   "id": 1, "name": "Sneakers",
#   "media": [
#     {"url": "...", "conversions": {...}, "srcsets": {...}, "placeholder_svg": "...", ...}
#   ]
# }
```

That's the whole API for the common case. Read on for conversions, multi-collection hosts, queued
work, and the standalone `Image` transform API.

---

## `HasMedia` — the model trait

### Declaring a collection

Set `__media_collection__` to the bucket name. That's all. Every read and write on this model
targets it — no per-call `collection=` arg.

```python
class Product(HasMedia, Model, Timestamps):
    __media_collection__ = "images"
```

> Put `HasMedia` **before** `Model` in the base list. The framework enforces this at class-definition
> time — wrong order raises `TypeError` immediately, so the silent `to_dict()` shadowing trap can't
> ship to production.

If you need MIME limits, size caps, conversions, or a fallback URL, override
`register_media_collections`:

```python
from arvel_image import HasMedia, MediaCollection, Conversion


class Product(HasMedia, Model, Timestamps):
    __media_collection__ = "images"

    def register_media_collections(self) -> None:
        (
            MediaCollection("images")
            .accept_mime_types(["image/jpeg", "image/png", "image/webp"])
            .max_file_size(5 * 1024 * 1024)               # 5 MB
            .use_fallback_url("/img/placeholder.svg")
            .with_conversions(
                Conversion("thumbnail").fit("cover", 150, 150).format("webp").quality(85),
                Conversion("card").fit("cover", 400, 300).generate_responsive_images(),
                Conversion("full").fit("contain", 1200, 900).quality(90),
            )
            .register_on(self)
        )
```

### Writing — `add_image()`

One call. It figures out the source type for you.

```python
await product.add_image(file_bytes, file_name="hero.jpg")  # bytes / bytearray / memoryview
await product.add_image(uploaded_file, file_name="hero.jpg")  # file-like (.read())
await product.add_image("/var/uploads/hero.jpg")               # local path
await product.add_image("https://cdn.example.com/img.png")     # HTTP(S), SSRF-guarded
await product.add_image("data:image/png;base64,iVBORw0KGgo...")  # data URI
```

SSRF guard rejects `file://`, `ftp://`, loopback, and private-IP URLs out of the box.

### Advanced uploads — `image_builder()`

When you need custom properties, a specific disk, a queued conversion run, or responsive variants
toggled per-upload, switch to the builder:

```python
media = await (
    product
    .image_builder(file_bytes, file_name="hero.jpg")
    .with_custom_properties({"alt": "Hero shot", "role": "primary"})
    .to_disk("s3")
    .with_responsive_images()
    .queued()                           # offload conversions to the queue
    .save()                             # terminate; defaults to __media_collection__
)
```

`image_builder` only accepts in-memory sources (bytes, path, file-like). Use `add_image` directly
for URLs or base64.

### Reading

Everything reads from the eager-loaded `media` relation. Load it once with `.with_("media")` (per
query) or `.load("media")` (per instance / collection), then call as many sync helpers as you want
— no extra queries.

```python
product = await Product.with_("media").find(pid)

product.get_media()             # list[Media] for __media_collection__, ordered
product.first_media             # Media | None
product.last_media              # Media | None
product.image_url()             # str | None (original of first media)
product.image_url("thumbnail")  # str | None (named conversion, falls back gracefully)
product.image_url("thumbnail", fallback="/img/default.png")
```

### Deleting

```python
await product.first_media.delete()    # one row + its files
await product.clear_images()          # everything in __media_collection__
```

### Serializing

`HasMedia.to_dict()` overrides the base `to_dict()` and appends a serialized `media` array when the
relation is eager-loaded. No kit-side serializers, no manual `[m.to_dict() for m in product.media]`.

```python
return product.to_dict()
# {
#   "id": 1,
#   "name": "Sneakers",
#   "media": [
#     {
#       "id": "42",
#       "uuid": "0193...",
#       "collection_name": "images",
#       "file_name": "hero.jpg",
#       "mime_type": "image/jpeg",
#       "size": 184320,
#       "url": "https://cdn.example.com/42/hero.jpg",
#       "conversions": {"thumbnail": "...", "card": "...", "full": "..."},
#       "srcsets": {"card": "...100w, ...400w, ...800w"},
#       "placeholder_svg": "data:image/svg+xml;base64,...",
#       "custom_properties": {"alt": "Hero shot"},
#       "order": 1,
#       "created_at": "2026-06-04T00:21:00+00:00"
#     }
#   ]
# }
```

If `media` wasn't eager-loaded, the key is absent — never a surprise N+1 in your serializer.

---

## Conversions

Conversions are declared on the collection and run automatically after every `add_image`.

```python
Conversion("thumbnail").fit("cover", 150, 150).format("webp").quality(85)
Conversion("card").fit("cover", 400, 300).generate_responsive_images()
Conversion("full").fit("contain", 1200, 900).quality(90)
Conversion("narrow").to_width(400)                       # height adjusts to keep aspect
```

Available chain methods:

| Method | Description |
|---|---|
| `.fit(mode, width, height)` | `"cover"` or `"contain"` |
| `.resize(width=…, height=…)` | Stretch to exact size |
| `.crop(left=…, top=…, width=…, height=…)` | Fixed window |
| `.to_width(px)` / `.to_height(px)` | Single-axis, preserves aspect ratio |
| `.format(fmt)` | `"jpeg"`, `"png"`, `"webp"`, `"gif"` |
| `.quality(q)` | 1–100 |
| `.generate_responsive_images()` | Emit `<srcset>` variants for this conversion |

### Responsive images

Enable per upload, per conversion, or per collection:

```python
# per upload
await product.image_builder(bytes_, file_name="hero.jpg").with_responsive_images().save()

# per conversion
Conversion("card").fit("cover", 400, 300).generate_responsive_images()

# per collection (applies to the original)
MediaCollection("images").generate_responsive_images().register_on(self)
```

Then in templates:

```html
<img
  src="{{ media.url('card') }}"
  srcset="{{ media.srcset('card') }}"
  sizes="(min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw"
  loading="lazy"
>
```

A blurred SVG placeholder is generated automatically — read it from `media.placeholder_svg()` or
the serialized `placeholder_svg` field.

### Queued conversions

For uploads where the user doesn't need to wait for thumbnails:

```python
await product.image_builder(bytes_, file_name="hero.jpg").queued().save()
```

A `QueuedConversionJob` runs the conversions in the background. The original is available
immediately; conversions appear as the job processes them.

---

## `MediaCollection` — full reference

```python
(
    MediaCollection("gallery")
    .only_keep_latest(10)                           # prune older rows beyond N
    .accept_mime_types(["image/jpeg", "image/png"])
    .max_file_size(5 * 1024 * 1024)                 # bytes
    .use_disk("s3")                                 # originals
    .use_conversions_disk("s3-public")              # derivatives
    .use_fallback_url("/img/placeholder.jpg")
    .generate_responsive_images()                   # default for uploads
    .with_conversions(
        Conversion("thumb").fit("cover", 150, 150),
    )
    .register_on(self)
)
```

Pass `single_file=True` to the constructor or chain `.single_file()` to make every upload replace
the previous one. `single_file` and `only_keep_latest(N)` are mutually exclusive — pick the right
one for the model.

---

## Multi-collection hosts

The single-collection case is the default. When a model genuinely needs more than one bucket
(say, a `User` with both `avatar` and `cover`), use the explicit `_in(...)` helpers:

```python
class User(HasMedia, Model, Timestamps):
    __media_collection__ = "avatar"   # default for add_image / get_media / first_media

    def register_media_collections(self) -> None:
        MediaCollection("avatar", single_file=True).register_on(self)
        MediaCollection("cover", single_file=True).register_on(self)


await user.add_image(file_bytes, file_name="me.jpg")                       # → avatar
await user.add_image(file_bytes, file_name="bg.jpg", collection="cover")   # → cover

user.get_media()                  # avatar
user.media_in("cover")            # cover
user.media_in("*")                # every collection merged

await user.clear_images()         # clears avatar
await user.clear_media_in("cover")
await user.clear_media_in_except("cover", kept=keep_me)
```

### Sharing media across hosts — `__morph_class__`

Two model classes can share the *same* media rows when one is a read-only view of the other. Set
`__morph_class__` on both to the canonical name, and reads + writes both resolve to those rows:

```python
class Product(HasMedia, Model, Timestamps):
    __tablename__ = "products"
    __media_collection__ = "images"
    __morph_class__ = "Product"           # canonical


class ProductCatalog(HasMedia, Model, Timestamps):
    """Read-only materialized view over `products`."""
    __tablename__ = "products_catalog"
    __media_collection__ = "images"
    __morph_class__ = "Product"           # share Product's media rows


# Either class sees the same media.
await ProductCatalog.with_("media").first()           # batches against "Product"
await product_catalog.image_url("thumbnail")          # served from cache
await product.add_image(bytes_, file_name="hero.jpg") # writes under "Product"
```

`Media.copy(target)` and `Media.move(target)` honor the target's `__morph_class__` too, so a row
moved to a host with a different morph class records the *destination's* morph alias as its
`model_type`.

---

## `Media` — what each row gives you

```python
m: Media = product.first_media

m.url()                          # original
m.url("thumbnail")               # named conversion
m.srcset()                       # original responsive variants
m.srcset("card")                 # conversion-level responsive variants
m.placeholder_svg()              # blurred SVG placeholder, base64 data URI
m.has_generated_conversion("thumbnail")
m.to_dict()                      # full payload (see above)

await m.delete()                 # row + files
await m.copy(other_host)         # duplicate to another HasMedia model
await m.move(other_host)         # move ownership
```

---

## `Image` — standalone transforms

`Image` is a fluent, lazy wrapper around Pillow. No subprocesses, no shelling out. Use it directly
when you need a one-off transform that isn't tied to a model.

```python
from arvel_image import Image

(
    Image.load("photo.jpg")
    .optimize()                      # bake EXIF orientation into pixels
    .fit("cover", 800, 600)
    .format("webp")
    .quality(85)
    .save("photo.webp")
)

thumbnail: bytes = (
    Image.load("avatar.jpg").fit("cover", 256, 256).format("png").to_bytes()
)
```

The chain is lazy — nothing decodes until a terminal runs. In an async handler, use the `*_async`
terminals to offload the whole pipeline to a worker thread:

```python
data: bytes = await (
    Image.load(source).fit("cover", 256, 256).format("webp").to_bytes_async()
)

await Image.load(source).fit("cover", 256, 256).save_async("avatar.webp")
```

### Operations

| Method | Description |
|---|---|
| `Image.load(source)` | Path, file-like, or `bytes` |
| `.fit(mode, width, height)` | `"cover"` or `"contain"` |
| `.resize(width=…, height=…)` | Stretch to exact size |
| `.crop(left=…, top=…, width=…, height=…)` | Fixed window |
| `.to_width(px)` / `.to_height(px)` | Single-axis, preserves aspect ratio |
| `.format(fmt)` | `"jpeg"`, `"png"`, `"webp"`, `"gif"` |
| `.quality(q)` | 1–100 (honoured by JPEG and WEBP) |
| `.optimize()` | Bake EXIF orientation into pixels (`exif_transpose`) |
| `.strip_exif()` | Explicitly zero out EXIF / XMP on encode |
| `.save(path)` / `.save_async(path)` | Write to disk |
| `.to_bytes()` / `.to_bytes_async()` | Return raw bytes |

Properties: `.width` and `.height` return the current size (force a decode).

---

## Recipe: a product detail endpoint

End-to-end, what it looks like in a real handler:

```python
from arvel.routing import Route

from app.models.product import Product


@Route.get("/products/{id}")
async def show(id: int) -> dict:
    product = await (
        Product.where(Product.id == id)
        .with_("media", "category", "vendor")
        .first_or_fail()
    )
    return product.to_dict()
```

Frontend gets `id`, `name`, `category`, `vendor`, and a `media` array with URLs, conversions, and
srcsets — in one query, zero N+1, zero serializer code.

---

## License

MIT — see [LICENSE](../../LICENSE).
