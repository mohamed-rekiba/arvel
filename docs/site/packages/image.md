# arvel-image

<a name="introduction"></a>
## Introduction

`arvel-image` packs two features into one package:

- **Image** — a fluent, Pillow-based wrapper for resize/crop/fit/format/quality. Lazy chain with both sync and `await`able terminals, no shelling out.
- **Media library** — a polymorphic `media` table plus a runtime (`HasMedia`, collections, conversions, responsive variants) for attaching files to any model with a DX that needs almost no boilerplate.

<a name="a-quick-tour"></a>
## A Quick Tour

One class attribute, one upload call — conversions and disk paths are handled for you:

```bash
uv add "arvel[image]"
arvel vendor:publish --tag=arvel-image
arvel migrate
```

```python
from arvel.database import Model, Timestamps, id_, string
from arvel_image import HasMedia


class Product(HasMedia, Model, Timestamps):
    __tablename__ = "products"
    __media_collection__ = "images"

    id: int = id_()
    name: str = string(120)


product = await Product.create(name="Mug")
await product.add_image(file_bytes, file_name="mug.jpg")

product = await Product.with_("media").find(product.id)
product.image_url("thumbnail")    # conversion URL when registered
```

> [!IMPORTANT]
> Put `HasMedia` **before** `Model` in the MRO so `HasMedia.to_dict()` chains into `Model.to_dict()` via `super()`.

<a name="installation"></a>
## Installation

```bash
uv add "arvel[image]"
```

For HEIF/HEIC support:

```bash
uv add "arvel[image-heif]"
```

Register the provider and publish the migration:

```python
# bootstrap/providers.py
from arvel_image import ImageServiceProvider

providers = [ImageServiceProvider]
```

```bash
arvel vendor:publish --tag=arvel-image
arvel migrate
```

`ImageServiceProvider` registers a `PathGenerator` and `ConversionRunner` and publishes the `media` table migration.

<a name="manipulating-images"></a>
## Manipulating Images

`Image` is a fluent Pillow wrapper. The chain is lazy — `load` and the pixel operations just record what to do; nothing decodes or transforms until a terminal runs. Chain operations and terminate with `to_bytes()` / `save()` (sync) or `to_bytes_async()` / `save_async()` (`await`able):

```python
from arvel_image import Image

out = (
    Image.load(source_bytes)        # bytes, path, or file object
    .fit("cover", 400, 300)
    .quality(85)
    .format("webp")
    .to_bytes()
)
```

Operations: `resize(width=, height=)`, `fit(mode, width, height)`, `crop(left=, top=, width=, height=)`, `to_width(px)`, `to_height(px)`, `quality(value)`, `format(image_format)`, `optimize()`, `strip_exif()`. Output formats: `jpeg`/`jpg`, `png`, `webp`, `gif`. `.optimize()` bakes EXIF orientation into pixels via `exif_transpose`; `.strip_exif()` zeros out the EXIF/XMP blocks on encode.

Argument validation (`quality` range, `format` support, positive dimensions) fires eagerly when you call the method, so mistakes still fail fast. Building is side-effect free — calling a terminal twice replays the chain rather than mutating shared state.

Pillow's decompression-bomb guard is enabled by default. Tune or disable it globally when you trust your sources:

```python
from arvel_image import set_max_pixels

set_max_pixels(25_000_000)   # raise the pixel budget
set_max_pixels(None)         # disable (only for trusted inputs)
```

> [!TIP]
> `Image` is CPU-bound. In an async request handler, use the `*_async` terminals — they offload the whole pipeline (decode + transforms + encode) to a worker thread so you don't block the event loop:
>
> ```python
> data = await Image.load(source).fit("cover", 256, 256).format("webp").to_bytes_async()
> await Image.load(source).fit("cover", 256, 256).save_async("avatar.webp")
> ```

<a name="attaching-media"></a>
## Attaching Media to a Model

One class attribute, one upload call. Everything else is automatic.

```python
from arvel.database import Model, Timestamps, id_, string
from arvel_image import HasMedia


class Product(HasMedia, Model, Timestamps):
    __tablename__ = "products"
    __media_collection__ = "images"

    id: int = id_()
    name: str = string(120)


product = await Product.create(name="Mug")
await product.add_image(file_bytes, file_name="mug.jpg")
```

`add_image` is polymorphic — it figures out the source type for you:

```python
await product.add_image(file_bytes, file_name="mug.jpg")      # bytes / bytearray / memoryview
await product.add_image(upload, file_name="mug.jpg")           # file-like (.read())
await product.add_image("/var/uploads/mug.jpg")                # local path
await product.add_image("https://cdn.example.com/mug.png")     # HTTP(S), SSRF-guarded
await product.add_image("data:image/png;base64,iVBOR...")      # data URI
```

> [!IMPORTANT]
> Put `HasMedia` **before** `Model` in the MRO so `HasMedia.to_dict()` chains into `Model.to_dict()` via `super()`.

For MIME limits, size caps, conversions, or a fallback URL, override `register_media_collections`:

```python
from arvel_image import Conversion, HasMedia, MediaCollection


class Product(HasMedia, Model, Timestamps):
    __media_collection__ = "images"

    def register_media_collections(self) -> None:
        (
            MediaCollection("images")
            .accept_mime_types(["image/jpeg", "image/png", "image/webp"])
            .max_file_size(5 * 1024 * 1024)
            .use_fallback_url("/img/placeholder.svg")
            .with_conversions(
                Conversion("thumbnail").fit("cover", 150, 150).format("webp").quality(85),
                Conversion("card").fit("cover", 400, 300).generate_responsive_images(),
                Conversion("full").fit("contain", 1200, 900).quality(90),
            )
            .register_on(self)
        )
```

For advanced uploads (custom properties, queued conversions, disk override, responsive toggle), switch to the builder:

```python
media = await (
    product
    .image_builder(file_bytes, file_name="hero.jpg")
    .with_custom_properties({"alt": "Hero shot"})
    .to_disk("s3")
    .with_responsive_images()
    .queued()
    .save()                                # defaults to __media_collection__
)
```

`image_builder` accepts in-memory sources (bytes, path, file-like). Use `add_image` for URLs and base64.

<a name="reading-media"></a>
## Reading Media

After eager loading, every read serves from memory — zero per-host queries.

```python
product = await Product.with_("media").find(pid)

product.get_media()             # list[Media], ordered
product.first_media             # Media | None
product.last_media              # Media | None
product.image_url()             # str | None, original of first media
product.image_url("thumbnail")  # str | None, named conversion
product.image_url("thumbnail", fallback="/img/default.png")

await product.first_media.delete()   # one row + its files
await product.clear_images()         # everything in __media_collection__
await product.delete_preserving_media()   # delete host row; media rows stay (orphaned)
```

<a name="multi-collection"></a>
## Multi-Collection Hosts

The single-collection case is the default. When a model genuinely needs more than one bucket, use the explicit `_in(...)` helpers:

```python
class User(HasMedia, Model, Timestamps):
    __media_collection__ = "avatar"

    def register_media_collections(self) -> None:
        MediaCollection("avatar", single_file=True).register_on(self)
        MediaCollection("cover", single_file=True).register_on(self)


await user.add_image(bytes_, file_name="me.jpg")                      # → avatar
await user.add_image(bytes_, file_name="bg.jpg", collection="cover")  # → cover

user.get_media()                  # avatar
user.media_in("cover")            # cover
user.media_in("*")                # every collection merged

await user.clear_images()
await user.clear_media_in("cover")
await user.clear_media_in_except("cover", kept=keep_me)
```

<a name="eager-loading-media"></a>
## Eager Loading Media (avoiding N+1)

`media` is an ordinary `MorphMany`, so the framework's eager loading covers it. Calling `get_media()` inside a loop over a page of products without eager loading is a classic N+1 — one media query per row.

Like Eloquent's `with('media')`, eager loading is **two queries** — one for the rows, one `WHERE model_id IN (...)` for their media. The win is that the media query runs once for the whole page.

### `.with_("media")` — the query-builder way

Use this whenever you're fetching the hosts. It's the idiomatic form:

```python
products = await Product.where(is_active=True).with_("media").limit(20).get()

for product in products:
    # Served from memory — no extra query, no await.
    thumb = product.image_url("thumbnail")
```

This also works for a read-only **view model** that shares another model's media. Set `__morph_class__` so the view presents as the canonical model (see [Overriding the Morph Class](../orm/relationships.md#morph-class-override)); `.with_("media")` then batches against the canonical type, not the view's own name:

```python
# ProductCatalog sets __morph_class__ = "Product"; media is stored under "Product"
products = await ProductCatalog.where(is_active=True).with_("media").get()
```

Eager-load a relation and its media in one go — `media` is a plain `MorphMany`, so it nests like any other relation:

```python
items = await CartItem.where(cart_id=cart_id).with_("product.media").get()

for item in items:
    product = await item.product().first()       # from the eager cache
    thumb = product.image_url("thumbnail")
```

### `load("media")` — when you already hold the instances

```python
products = await ProductCatalog.where(is_active=True).get()  # no .with_("media")
await products.load("media")                                  # one batched query
```

Either way, `get_media`, `first_media`, `last_media`, and `image_url` read from the in-memory cache. Adding or clearing media on a host invalidates its cache, so a later read reflects the change.

<a name="serializing"></a>
## Serializing — Automatic

`HasMedia.to_dict()` overrides the base `to_dict()` and appends a serialized `media` array when the relation is eager-loaded. No kit-side serializers needed.

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
#       "url": "...",
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

When `media` isn't eager-loaded, the `media` key is absent — never a surprise N+1 inside a serializer.

<a name="responsive-images"></a>
## Responsive Images

Enable per upload, per conversion, or per collection.

```python
# per upload
await product.image_builder(bytes_, file_name="hero.jpg").with_responsive_images().save()

# per conversion
Conversion("card").fit("cover", 400, 300).generate_responsive_images()

# per collection (applies to the original)
MediaCollection("images").generate_responsive_images().register_on(self)
```

The width algorithm is file-size optimized: each step shrinks the width by `sqrt(0.7)` (~0.8367), stopping when the predicted file size drops below 10 KB or the width below 20 px.

Variants are stored under `{id}/responsive-images/` on the same disk as the original. The `responsive_images` column is `dict[str, {"urls": [...], "base64svg": str}]` keyed by `"original"` for the original and by the conversion name (e.g. `"card"`) for conversion-level variants. A tiny blurred JPEG wrapped in an SVG is the placeholder.

```python
srcset_orig  = media.srcset()              # "original" group
srcset_card  = media.srcset("card")        # conversion-level group
placeholder  = media.placeholder_svg()     # data:image/svg+xml;base64,...
```

When `.queued()` is combined with `.with_responsive_images()`, variant generation is also deferred — the request returns immediately and `QueuedConversionJob` does the work.

<a name="regenerating-conversions"></a>
## Regenerating Conversions

`MediaLibrary.regenerate(host=...)` re-runs conversions, e.g. after you change a collection's definition:

```python
from arvel_image import MediaLibrary

count = await MediaLibrary().regenerate(host=product, collection="images")
```

<a name="data-model"></a>
## Data Model

`Media` (table `media`) is polymorphic: `model_type` + `model_id` point back to the owner, with `collection_name`, `disk`, `generated_conversions`, `responsive_images`, and an `order_column`.

<a name="errors"></a>
## Errors

Every exception arvel-image raises inherits from `MediaError`. Catch the base for "anything from this package," catch a subclass when you want to react differently (e.g. retry vs reject).

| Exception | Full path | When it raises | What the message contains | Recommended response |
|---|---|---|---|---|
| `MediaError` | `arvel_image.MediaError` | Catch-all base. Direct raises happen for source-coercion errors (missing `file_name`, unsupported source type, unreadable file path, invalid base64, file:// or other non-HTTP scheme). | The offending input (file path, scheme, source type). | Treat as a 4xx — the caller gave us something we can't ingest. |
| `UnknownCollectionError` | `arvel_image.UnknownCollectionError` | The host declares one or more collections via `register_media_collections`, and the requested collection name isn't among them. | The collection name and the host class with its declared collections. | Programmer error — fix the call site to use a registered name, or register the collection. |
| `InvalidMimeTypeError` | `arvel_image.InvalidMimeTypeError` | The file's sniffed MIME doesn't pass the collection's `accept_mime_types(...)` allowlist, **or** (URL fetcher) the server's `Content-Type` header disagrees with what Pillow sniffs from the bytes. | The claimed MIME, the sniffed MIME, and the offending URL or file name. | Reject the upload as a 415 to the end user. For URL fetches this is the SSRF-adjacent "the server is lying" signal — don't auto-retry. |
| `FileTooLargeError` | `arvel_image.FileTooLargeError` | The upload exceeds the collection's `max_file_size` cap, the URL fetcher's `max_bytes` cap (streamed body or advertised `Content-Length`), or the decoded size of a base64 source exceeds `max_bytes`. | The cap, the actual size we saw, the file name, and (for URL sources) the userinfo-stripped URL. | 413 to the end user. The collection's cap is intentional — don't bump it without a reason. |
| `ConversionFailedError` | `arvel_image.ConversionFailedError` | A `Conversion` pipeline raised mid-run (corrupt source, unsupported format, Pillow refused). The original exception is chained via `__cause__`. | The conversion name and the media id; the wrapped exception is on `__cause__`. | Log + 5xx. The upload itself succeeded; just the derived variant failed. The original media row is intact. |
| `UnsupportedFormatError` | `arvel_image.UnsupportedFormatError` | Lives in `arvel_image.image`, raised by the fluent `Image` API when asked to encode/decode a format Pillow doesn't support (e.g. AVIF without `pillow-heif` installed). | The format name and the install hint when there's a known extension. | Install the optional extra (`pip install pillow-heif`) or reject the format at the API edge. |

The `MediaError` base sits in `arvel_image.media.exceptions` if you want to catch it deeper in a stack. The kit's `app/services/media_service.py` is the canonical example — it catches `MediaError` and returns a `ProblemDetails` 4xx response.

<a name="gotchas"></a>
## Gotchas

- `add_image` rejects non-HTTP URL schemes (`file://`, `ftp://`, …) and refuses loopback and private-IP destinations. DNS rebinding is still a documented limitation — don't pass fully untrusted URLs.
- `HasMedia.to_dict()` only appends `media` when the relation is eager-loaded. If you forget `.with_("media")`, the serialized payload silently omits the key — which is the safe default, but check your queries when an expected payload is missing media.
- Put `HasMedia` **before** `Model` in the class MRO. The framework now enforces this at class-definition time — wrong order raises `TypeError` immediately instead of silently shadowing `to_dict()`.
