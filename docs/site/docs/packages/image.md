# arvel-image

<a name="introduction"></a>
## Introduction

`arvel-image` packs two features into one package:

- **Image** — a fluent, Pillow-based wrapper for resize/crop/fit/format/quality. Lazy chain with both sync and `await`able terminals, no shelling out.
- **Media library** — a polymorphic `media` table plus a runtime (`HasMedia`, collections, conversions) for attaching files to any model, modeled after Spatie's Laravel Media Library.

<a name="installation"></a>
## Installation

```bash
uv add "arvel[image]"
```

For HEIF/HEIC support, add the extra:

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

`ImageServiceProvider` binds a `PathGenerator` and `ConversionRunner`, and publishes the `media` table migration.

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

Operations: `resize(width=, height=)`, `fit(mode, width, height)`, `crop(left=, top=, width=, height=)`, `quality(value)`, `format(image_format)`, `optimize()`. Output formats: `jpeg`/`jpg`, `png`, `webp`, `gif`.

Argument validation (`quality` range, `format` support, positive dimensions) fires eagerly when you call the method, so mistakes still fail fast. Because building is side-effect free, an `Image` is reusable — calling a terminal twice replays the chain rather than mutating shared state.

> [!TIP]
> `Image` is CPU-bound. In an async request handler, use the `*_async` terminals — they offload the whole pipeline (decode + transforms + encode) to a worker thread so you don't block the event loop:
>
> ```python
> data = await Image.load(source).fit("cover", 256, 256).format("webp").to_bytes_async()
> await Image.load(source).fit("cover", 256, 256).save_async("avatar.webp")
> ```

<a name="attaching-media"></a>
## Attaching Media to a Model

Mix in `HasMedia` and declare your collections in `register_media_collections`:

```python
from arvel.database import Model, Timestamps, id_, string
from arvel_image import Conversion, HasMedia, MediaCollection


class Product(Model, HasMedia, Timestamps):
    __tablename__ = "products"
    id: int = id_()
    name: str = string(120)

    def register_media_collections(self) -> None:
        (
            MediaCollection("images")
            .with_conversions(
                Conversion("thumb").fit("cover", 150, 150).quality(85),
                Conversion("card").fit("cover", 400, 300).quality(85),
            )
            .register_on(self)
        )
```

Add and read files:

```python
product = await Product.create(name="Mug")

media = await product.add_media(file_bytes, file_name="mug.jpg").to_media_collection("images")

url = await product.get_media_url("images", conversion="thumb")
items = await product.get_media("images")
await product.clear_media_collection("images")
```

Ingest helpers: `add_media`, `add_media_from_url`, `add_media_from_base64`, `add_media_from_disk`, `add_media_from_string`. A `single_file=True` collection keeps only the latest file (e.g. an avatar).

Bytes are stored via the [`Storage`](../features/storage.md) facade, so the disk is whatever you've configured. Conversions run on a background thread.

<a name="eager-loading-media"></a>
## Eager Loading Media (avoiding N+1)

`get_media` queries the `media` table once per host. Calling it inside a loop over a
page of products is a classic N+1 — one media query per row. The fix is eager loading,
exactly as in Eloquent: pull all the media in a single batched query up front.

Like Eloquent's `with('media')`, eager loading is still **two queries** — one for the
rows, one `WHERE model_id IN (...)` for their media. It's not a join. The win is that the
media query runs once for the whole page instead of once per row.

### `.with_("media")` — the query-builder way

Reach for this whenever you're fetching the hosts. It's the idiomatic form:

```python
products = await Product.where(is_active=True).with_("media").limit(20).get()

for product in products:
    # served from memory — no extra query
    thumb = await product.get_media_url("images", conversion="thumb")
```

This also works for a read-only **view model** that shares another model's media. Set
`__morph_class__` so the view presents as the canonical model (see
[Overriding the Morph Class](../orm/relationships.md#morph-class-override)); `.with_("media")`
then batches against the canonical type, not the view's own name:

```python
# ProductCatalog sets __morph_class__ = "Product"; media is stored under "Product"
products = await ProductCatalog.where(is_active=True).with_("media").get()
```

Eager-load a relation and its media in one go — `media` is a plain `MorphMany`, so it
nests like any other relation:

```python
items = await CartItem.where(cart_id=cart_id).with_("product.media").get()

for item in items:
    product = await item.product().first()       # from the eager cache
    thumb = await product.get_media_url("images", conversion="thumb")  # cached too
```

### `load("media")` — when you already hold the instances

Media is a `MorphMany`, so the framework's own lazy eager loading covers it. Use
`load("media")` on an in-hand model or collection — Eloquent's `$model->load('media')`
/ `$collection->load('media')` — when you didn't eager-load up front:

```python
products = await ProductCatalog.where(is_active=True).get()  # no .with_("media")
await products.load("media")  # one query, fills the same eager cache
```

Either way, `get_media`, `get_first_media`, `get_last_media`, and `get_media_url` then
read from the in-memory cache for those hosts. Attaching or clearing media on a host
invalidates its cache, so a later read reflects the change.

<a name="regenerating-conversions"></a>
## Regenerating Conversions

`MediaLibrary.regenerate(host=...)` re-runs conversions, e.g. after you change a collection's definition:

```python
from arvel_image import MediaLibrary

count = await MediaLibrary().regenerate(host=product, collection="images")
```

<a name="data-model"></a>
## Data Model

`Media` (table `media`) is polymorphic: `model_type` + `model_id` point back to the owner, with `collection_name`, `disk`, `generated_conversions`, and an `order_column`.

<a name="gotchas"></a>
## Gotchas

- The mixin is `HasMedia` (alias `HasMediaMixin`) — there is no `InteractsWithMedia`.
- `add_media_from_url` has an SSRF guard, but DNS rebinding is a documented limitation — don't pass fully untrusted URLs.
- The `responsive_images` column exists but no responsive-image generation logic ships yet.
- Only `create_media_table.py` is published. A separate `001_alter_media_model_id.py` migration exists for upgrading older databases and isn't auto-published.
