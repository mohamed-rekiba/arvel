# ORM Collections

When the query builder returns multiple results, it returns a `ModelCollection` — a `list` subclass that knows about your model. It includes all the methods of [Collection](collections.md), plus a few that only make sense in the model context.

## Returning a collection

```python
posts: ModelCollection[Post] = await Post.get()
```

`ModelCollection[Post]` is fully typed: `posts[0].title` and `posts.first().title` both type-check.

## Working with related data

Once you've eager-loaded relations, the collection gives you batch-friendly accessors:

```python
posts = await Post.with_("author").get()

# Group by author
by_author = posts.group_by(lambda p: p.author.id)

# Pluck author IDs (handles loaded relations automatically)
author_ids = posts.pluck("author.id").unique()
```

## Loading missing relations

You can lazily load relations onto an existing collection — useful when the eager-load decision happens later:

```python
posts = await Post.get()
await posts.load("author", "comments")

for post in posts:
    print(post.author.name, len(post.comments))
```

This issues exactly two extra queries (one per relation), regardless of collection size. No N+1.

## Bulk operations

```python
posts = await Post.where(published=False).get()
await posts.delete()                # bulk-delete all rows

await posts.each(lambda p: p.recompute_score())   # apply to each, in-order
await posts.each_async(lambda p: external_api.notify(p), concurrency=5)
```

`each_async` runs concurrently with a configurable cap — useful for I/O-bound side effects.

## Serializing

```python
data = posts.to_dict()      # list of dicts
json_str = posts.to_json()
```

Each model's `to_dict()` is invoked. For custom shapes, use a [JsonResource](responses.md#json-resources) collection.

## Where to next?

- [Collections](collections.md) — the base collection class and its full method list.
- [Relationships](arvent-relationships.md) — `load`, `with_`, and friends.
- [Responses](responses.md) — converting collections to JSON responses.
