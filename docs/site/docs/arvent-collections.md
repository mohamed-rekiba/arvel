# ORM Collections

When the query builder returns multiple results, it returns a `ModelCollection` — a `list` subclass that knows about your model. It includes all the methods of [Collection](collections.md), plus a few that only make sense in the model context.

## Returning a collection

```python
posts = await Post.get()   # ModelCollection[Post] at runtime
```

`Post.get()` / `Post.all()` are typed `list[Post]`, so element access (`posts[0].title`) type-checks and iteration works. The runtime object is a `ModelCollection`, so the model-aware helpers below are available too — annotate the variable `ModelCollection[Post]` if you want those to type-check:

```python
posts: ModelCollection[Post] = await Post.get()
posts.model_keys()
```

## Working with related data

Once you've eager-loaded relations, the collection gives you batch-friendly accessors:

```python
posts = await Post.get()

# Group by the foreign key column — no relation load needed
by_author = posts.group_by(lambda p: p.author_id)

# Pluck author IDs straight off the column
author_ids = posts.map(lambda p: p.author_id).unique()
```

`pluck(key)` reads a single attribute (`getattr(item, key)`) — it doesn't walk dotted paths. For nested values, `map` with a lambda as above.

## Loading missing relations

You can lazily load relations onto an existing collection — useful when the eager-load decision happens later:

```python
posts = await Post.get()
await posts.load("author", "comments")

for post in posts:
    author = await post.author().first()      # served from the cache
    comments = await post.comments().get()    # served from the cache
    print(author.name, len(comments))
```

`load` batches: pivot, morph, and one-of-many relations load through the descriptor batch loader, plain relations through one `select(... pk IN keys)` + `selectinload` — a fixed number of queries regardless of collection size. No N+1. `load_missing` loads only relations not already populated, and raises `UnknownRelationError` on a misspelled name.

## Key-aware lookups

`ModelCollection` operations key off the primary key (`get_key`), not object identity:

```python
posts = await Post.order_by("id").get()

posts.model_keys()          # [1, 2, 3]
posts.find(2)               # the post with id == 2 (or None)
posts.contains(2)           # True
posts.contains(some_post)   # accepts a model instance too
posts.only(1, 3)            # collection of posts 1 and 3
posts.except_(2)            # everything but post 2

published = await Post.where(Post.published == True).get()
posts.diff(published)       # posts not in `published` (by key)
posts.intersect(published)  # posts also in `published` (by key)
```

These are the same `find`/`contains`/`only`/`except_`/`diff`/`intersect` methods as the base [Collection](collections.md) — `ModelCollection` overrides them to compare by primary key instead of by value or object identity.

## Re-querying

```python
# A query scoped to exactly these rows
count = await posts.to_query().where(Post.views > 100).count()

# Re-fetch from the DB (picks up bulk updates), preserving order
posts = await posts.fresh("author")
```

## Hiding fields across a set

```python
users.make_hidden("email")    # hide on every member's to_dict()
users.make_visible("email")   # and unhide
```

## Bulk operations

`to_query()` turns the collection back into a builder scoped to its rows, so write operations run as one statement instead of a loop:

```python
posts = await Post.where(published=False).get()
await posts.to_query().delete()     # one DELETE ... WHERE id IN (...)
await posts.to_query().update({"archived": True})
```

For per-row work, iterate — `ModelCollection` is a plain `list`:

```python
for post in posts:
    post.recompute_score()
```

## Serializing

`to_json()` serializes the whole collection; each member's `to_dict()` is invoked:

```python
json_str = posts.to_json()
data = [p.to_dict() for p in posts]   # list of dicts
```

For custom shapes, use a [JsonResource](responses.md#json-resources) collection.

## Where to next?

- [Collections](collections.md) — the base collection class and its full method list.
- [Relationships](arvent-relationships.md) — `load`, `with_`, and friends.
- [Responses](responses.md) — converting collections to JSON responses.
