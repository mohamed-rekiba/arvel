# Media

Almost every app deals with files people upload — an avatar, a post's cover image, a gallery, the
occasional PDF or video clip. Doing that by hand gets tedious fast: resize the image, pick a
filename, push it to storage, remember where it went, generate a thumbnail, and somehow tie it all
back to the user or post it belongs to.

arvel's media layer handles that for you, at two levels:

- **Low level** — `Image` and `Video`, thin fluent wrappers over [Pillow](https://python-pillow.org)
  and [PyAV](https://github.com/PyAV-Org/PyAV) for resizing, cropping, encoding, and probing.
- **High level** — the `HasMedia` mixin, which **attaches files to your models**: upload a file,
  and arvel stores it, generates the thumbnails you asked for, and records it as a row you can query
  and serve.

Reach for the low level when you just need to transform some bytes; reach for `HasMedia` when a file
*belongs* to something.

!!! note "Needs the `[image]` and/or `[video]` extra"
    Everything here is **opt-in** and imported lazily. Image transforms and model thumbnails need
    Pillow (`uv add 'arvel[image]'`); video probing needs PyAV (`'arvel[video]'`). `HasMedia` also
    uses a [storage disk](storage.md) and a [database](database/index.md) extra — full set below.

## Installation

The media engines are **optional dependencies** — kept out of the core and imported only when you
use them, so `import arvel` stays light. Install the ones you need:

```bash
uv add 'arvel[image]'    # image manipulation + media conversions  (Pillow)
uv add 'arvel[video]'    # video probing                           (PyAV)
uv add 'arvel[media]'    # convenience alias — currently the image stack
```

Without the relevant extra, the first call that touches the engine raises an `ImportError`.

Two more, depending on how you use `HasMedia`:

- **Storage** — files land on a disk. The local disk needs nothing extra; a cloud disk needs its
  driver: `arvel[s3]`, `arvel[gcs]`, or `arvel[azure]` (see [File Storage](storage.md)).
- **Database** — each file is recorded as a `Media` row, so you'll already have a database extra
  installed (`arvel[postgres]` / `arvel[sqlite]`; see [Database & ORM](database/index.md)).

## Transforming images

`Image` wraps a single picture. Open it from raw bytes (an upload) or a path, transform it, and
encode it back to bytes ready for storage:

```python
from arvel.media import Image

img = Image.open(uploaded_bytes)
img.width, img.height                       # read its dimensions

cover = img.resize(1200, 630).convert("RGB").encode("JPEG")   # -> bytes
```

Every transform returns a **new** `Image` — the original is never mutated — which is exactly why
they chain so cleanly:

```python
thumb = Image.open(uploaded_bytes).crop(0, 0, 400, 400).resize(200, 200).convert("RGB").encode("PNG")
```

| Method | What it does |
|--------|--------------|
| `Image.open(bytes \| path)` | load an image |
| `Image.make(w, h, color="white")` | a blank canvas |
| `resize(w, h)` | scale to a size |
| `crop(left, top, right, bottom)` | cut out a box |
| `convert(mode)` | change colour mode — `"RGB"`, `"L"` (greyscale), … |
| `encode(format="PNG")` | render to bytes — `"PNG"`, `"JPEG"`, … |

A common end-to-end task — make a square avatar and store it — is just a chain plus a
[Storage](storage.md) write:

```python
from arvel.media import Image
from arvel import Storage

async def save_avatar(user, upload_bytes):
    jpeg = Image.open(upload_bytes).resize(256, 256).convert("RGB").encode("JPEG")
    await Storage.disk("s3").put(f"avatars/{user.id}.jpg", jpeg)
```

## Probing video

`Video` opens a container and reads its metadata — duration, stream layout — **without decoding**
the whole file, so it's cheap even for large clips:

```python
from arvel.media import Video

clip = Video.open("episode.mp4")
clip.duration()              # total length
clip.streams_info()          # [{"type": "video"}, {"type": "audio"}]
clip.close()                 # release the file handle
```

`Video.open` holds an OS file handle, so call `close()` when you're done (or keep the work brief) to
avoid leaking handles under load.

## Attaching files to a model

This is the part you'll reach for most. Mix `HasMedia` into a model and its files become
first-class: stored on a [disk](storage.md), grouped into named **collections**, and recorded as
`Media` rows you can query, serve, and delete.

```python
from arvel import Model
from arvel.media import HasMedia, MediaConversion

class Post(HasMedia, Model):
    __fields__ = {"title": str}

    def register_media_conversions(self) -> list[MediaConversion]:
        return [MediaConversion("thumb", width=320, height=240)]
```

You'll also need a `media` table once, in a migration — the polymorphic owner
(`model_type`/`model_id`), `collection_name`, `file_name`, `disk`, `size`, the JSON
`custom_properties` and `generated_conversions`, and `order_column`. Copy this:

```python
from arvel.database import Blueprint, Migration, Schema


class CreateMediaTable(Migration):
    def up(self, schema: Schema) -> None:
        def define(t: Blueprint) -> None:
            t.id()
            t.string("model_type").index()
            t.big_integer("model_id").index()
            t.string("collection_name").index()
            t.string("name")
            t.string("file_name")
            t.string("mime_type")
            t.string("disk")
            t.big_integer("size")
            t.json("custom_properties")
            t.json("generated_conversions")
            t.integer("order_column").default(value=0)
            t.timestamps()

        schema.create("media", define)

    def down(self, schema: Schema) -> None:
        schema.drop("media")
```

### Adding a file

`add_media` takes the raw bytes and a filename; `to_media_collection` stores them and returns the
`Media` row:

```python
media = await (
    post.add_media(upload_bytes, file_name="cover.png", mime_type="image/png")
        .to_media_collection("images")          # the collection name is yours to choose
)
```

A **collection** is just a label — `"images"`, `"attachments"`, `"downloads"` — so one model can keep
separate buckets of media. Pass `disk=` to choose where it lands (defaults to your default disk):

```python
await post.add_media(pdf_bytes, file_name="brief.pdf").to_media_collection("downloads", disk="s3")
```

You can name the media and attach arbitrary metadata before storing:

```python
await (
    post.add_media(upload_bytes, file_name="cover.png")
        .using_name("Launch cover")
        .with_custom_properties({"credit": "Jane Doe", "alt": "the product on a desk"})
        .to_media_collection("images")
)
```

### Conversions (thumbnails and friends)

A **conversion** is a derived version of the original — a thumbnail, a web-sized copy, a re-encoded
format. Declare them once per model in `register_media_conversions`, and arvel generates each one
**when the file is added**, storing it alongside the original:

```python
def register_media_conversions(self) -> list[MediaConversion]:
    return [
        MediaConversion("thumb", width=320, height=240),
        MediaConversion("web", width=1600, height=900, fmt="JPEG"),
    ]
```

`MediaConversion(name, *, width=None, height=None, fmt="PNG")` resizes (when both dimensions are
given) and encodes to `fmt`. Each generated conversion is recorded on the media and addressable by
name later.

### Reading media back, and getting URLs

Pull a collection's media, or just the first item — handy for a single cover or avatar:

```python
gallery = await post.get_media("images")            # [<Media …>], in upload order
cover   = await post.get_first_media("images")      # the first Media, or None
```

For URLs there are **two methods, on two different objects** — worth getting straight, because they
*look* similar:

```python
# on a Media you already hold — sync:
cover.get_url()             # the original's URL
cover.get_url("thumb")      # a named conversion's URL

# on the owning model — async, a convenience that grabs the first item for you:
await post.get_first_media_url("images")            # first image's original URL
await post.get_first_media_url("images", "thumb")   # first image's thumbnail URL
```

So `media.get_url(...)` answers "what's *this* file's URL?", while `post.get_first_media_url(...)`
is shorthand for "first item in the collection, then its URL." The second simply calls
`get_first_media(...)` and then `get_url(...)` for you.

!!! info "What the URL actually points at"
    `get_url()` returns the disk's configured `url` base joined to the file's path — so configure a
    `url` for any disk you serve media from:

    ```python
    # config/filesystems.py
    filesystems = {"disks": {"public": {"url": "https://cdn.example.com"}}}
    # → media.get_url("thumb") == "https://cdn.example.com/images/7/conversions/thumb.png"
    ```

    With no `url` configured, it falls back to the storage-relative **path** — fine for a private
    disk, but not directly browsable. (Driver-derived public URLs and signed S3 links are a planned
    addition.)

### Loading a list without N+1

`media` is a real relation, so when you render a *list* — a feed, an index, a gallery grid — load
everyone's media in **one** query instead of one-per-row:

```python
posts = await Post.with_("media").get()             # a single batched query for all media
for post in posts:
    await post.get_first_media_url("images", "thumb")   # answered from memory, no extra query
```

After `with_("media")`, `get_media` and `get_first_media` read the already-loaded data and filter in
memory, so the loop never touches the database again. `post.relation("media")` hands you the full
loaded list. The relation keys on `model_type`/`model_id`, so two different models that happen to
share an id never pick up each other's files.

If a model has several collections and you only need one, constrain the eager load so the query
fetches just that collection — pass the relation as a keyword with a callback:

```python
# only each post's "images" media comes back, in one query
posts = await Post.with_(media=lambda q: q.where(collection_name="images")).get()
```

That's general constrained eager loading, by the way — it works for any relation
(`with_(comments=lambda q: q.where(approved=True))`), not just media.

### Removing media

```python
await post.clear_media_collection("images")         # deletes the rows and their files (incl. conversions)
```

## Any file type — not just images

`add_media` stores **anything** — a video, a PDF, a zip. Adding, reading, URL-building, and clearing
all work the same regardless of type.

The one image-specific part is **conversions**: they run through Pillow, so arvel only generates them
for image media (decided by the mime type, or the file extension when no mime is given). Hand it a
`clip.mp4` and it's stored as-is, with no conversions and no error — arvel won't try to open a video
as a picture. (Generating a poster-frame thumbnail from a video — via ffmpeg — is a planned
follow-up.)

## Extending the media model

`media.get_url("thumb")` always works, but the conversion *names* (`thumb`, `cover`, `web`) are
yours, not the framework's — so arvel deliberately doesn't invent accessors for them. When you want
to read them as attributes (and have them show up in JSON), **subclass `Media`, add your own
accessors, and point your model at the subclass** with `__media_model__`:

```python
from arvel import Model, Attribute
from arvel.media import HasMedia, Media, MediaConversion

class PostMedia(Media):
    __table_name__ = "media"            # share the media table — see the warning below
    __appends__ = ["url", "thumb"]      # include these in to_dict() / to_json()

    def url(self) -> Attribute:
        return Attribute(get=lambda value, attrs: self.get_url())

    def thumb(self) -> Attribute:
        return Attribute(get=lambda value, attrs: self.get_url("thumb"))

class Post(HasMedia, Model):
    __media_model__ = PostMedia         # add_media + the media relation now use PostMedia
    def register_media_conversions(self) -> list[MediaConversion]:
        return [MediaConversion("thumb", width=320, height=240)]
```

Now your media reads like data, and the URLs serialize for free:

```python
media = await post.get_first_media("images")
media.url            # the original's URL — no parens, no get_url()
media.thumb          # the thumbnail's URL
media.to_dict()      # {..., "url": ..., "thumb": ...}
```

These use arvel's [`Attribute` accessor](database/index.md) API — a method annotated `-> Attribute` that
returns `Attribute(get=…)` — so they cooperate with casts, caching, and `__appends__` serialization,
which a plain `@property` would not.

!!! warning "Keep the subclass on the same table"
    arvel builds one database table per model class, so a bare `PostMedia(Media)` would map to its
    own `post_medias` table. Set `__table_name__ = "media"` on the subclass so it stays on the shared
    media table.

## Common mistakes & gotchas

- **Treating image transforms as in-place.** `img.resize(...)` returns a *new* image and leaves the
  original alone. Keep the result (`img = img.resize(...)`) or chain — don't call it and discard the
  return value.
- **Encoding to a format the colour mode can't hold.** Saving an `RGBA` image as `JPEG` fails;
  `convert("RGB")` first. The order `resize().convert("RGB").encode("JPEG")` is the safe one.
- **Confusing the two URL helpers.** `media.get_url(...)` is sync and lives on a `Media`;
  `post.get_first_media_url(...)` is async and lives on the owner. Different objects, similar names.
- **Expecting conversions on non-images.** A video or PDF stores fine but gets no thumbnails —
  generate those separately if you need them.
- **Forgetting the extras.** Images need the `[image]` extra (Pillow); video needs `[video]` (PyAV).
  Both are imported lazily, so `import arvel` stays light until you actually use them.
- **Leaking video handles.** `Video.open` holds a file handle — `close()` it.

## How it works

`Image` and `Video` are thin wrappers: each `Image` transform calls Pillow and returns a fresh
`Image` around the result (that's what makes the API immutable and chainable), and `Video` reads a
PyAV container's metadata without decoding it. Both libraries are heavy, so they load lazily the
first time you open something — `import arvel` never pays that cost.

`HasMedia` stores the bytes on a Storage disk and writes a `Media` row that records where the file
went, which collection it belongs to, and the paths of any generated conversions. Because that row
carries the polymorphic owner (`model_type`/`model_id`), media is just a relation — which is what lets
you eager-load it, query it, and swap in a custom `Media` subclass.

## See also

- [File Storage](storage.md) — the disks media is stored on, and how `url` bases are configured.
- [Database & ORM](database/index.md) — the models you attach media to, eager loading, and the `Attribute`
  accessors used to expose media URLs.
- [Validation](validation.md) — the `image` and `mimes` rules for validating uploads before you store them.
