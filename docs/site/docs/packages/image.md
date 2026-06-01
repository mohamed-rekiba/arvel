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
