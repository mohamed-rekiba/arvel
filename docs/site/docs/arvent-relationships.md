# ORM Relationships

Tables are often related to each other — a post belongs to a user, a user has many posts, a post has many tags. Arvel ships first-class support for the common relation types, including polymorphic and many-to-many.

## Two styles

Arvel has two complementary ways to declare relationships.

**Method style** — an instance method that returns a `QueryBuilder` you can further chain before executing. Use this for write paths, conditional filters, and paginated reads.

**Descriptor style** — a class-level descriptor (`has_many_attr`, `BelongsToMany`, `MorphOne`, `MorphMany`). Use this when you want to eager-load the relation with `with_()`, filter with `where_has()`, or count with `with_count()`.

The two styles are complementary — you can declare the same logical relation both ways on one model when you need both read and write ergonomics.

## Has many

### Method style (chainable queries, write path)

```python
from arvel.database import HasMany, Model


class User(Model):
    __tablename__ = "users"

    def posts(self) -> HasMany["Post"]:
        return self.has_many(Post)
```

```python
posts = await user.posts().get()
recent = await user.posts().order_by("-created_at").limit(5).get()

# Writing through the relation sets the FK automatically
new_post = await user.posts().create(title="hello", body="world")
await user.posts().save(existing_post)

# Batch writes
await user.posts().create_many([{"title": "a"}, {"title": "b"}])
await user.posts().save_many([draft1, draft2])
```

`save()`, `create()`, and their `_many` batch forms all go through `Model.save()` / `Model.create()`, so observer events (`creating` / `created` / `saving` / `saved`), mutators, and timestamps all run — writing through a relation is not a shortcut around the model lifecycle.

The method returns a `QueryBuilder` scoped to `WHERE user_id = user.id` — every builder method chains normally before the terminal `get()` / `first()` / `count()`.

### Descriptor style (eager loading, existence queries)

When you nearly always load posts alongside users — and want `with_()` or `where_has()` support — declare it as a class attribute instead:

```python
from typing import Any
from arvel.database import Model, has_many_attr


class User(Model):
    __tablename__ = "users"

    posts: list[Any] = has_many_attr("Post", fk="user_id")
```

`has_many_attr` automatically:

- Builds the SA `relationship()` with the correct `primaryjoin`, resolved lazily through the mapper registry (safe for circular imports).
- Sets `lazy="raise_on_sql"` — accessing the attribute on an instance that wasn't loaded with `with_()` raises `sqlalchemy.exc.InvalidRequestError` immediately instead of issuing a silent query.
- Sets `viewonly=True` — the collection is read-only; writes still go through the method-style relation.

```python
# one query — no N+1
users = await User.with_("posts").all()

for user in users:
    print(user.posts)   # already loaded, no extra query

# Accessing without eager loading raises, never silent-queries
user = await User.find(1)
_ = user.posts          # raises InvalidRequestError
```

Use `where_has`, `doesnt_have`, and `has` with the class-level attribute:

```python
# Users who have at least one post
active = await User.where_has(User.posts).all()

# Users with no posts
empty = await User.doesnt_have(User.posts).all()

# Users with at least 5 posts
prolific = await User.has(User.posts, ">=", 5).all()

# Users with a post matching a condition
with_published = await User.where_has(
    User.posts, lambda q: q.where(Post.status == "published")
).all()
```

The annotation (`list[Any]`, `list[Post]`, or just `Any`) has no effect on runtime behaviour — use whatever helps your type checker.

## Has one

```python
from arvel.database import HasOne, Model


class User(Model):
    def profile(self) -> HasOne["Profile"]:
        return self.has_one(Profile)
```

```python
profile = await user.profile().first()

# Write through the relation
new_profile = await user.profile().create(bio="...")
```

FK is inferred as `user_id` by default. Pass `foreign_key="..."` to override.

### Non-`id` primary keys

`has_one`, `has_many`, and `belongs_to` resolve the local/owner key from the
model's actual primary key, not a hardcoded `id`. A model keyed on `uuid` or a
string `slug` works without extra config — the inferred FK follows the key name
(e.g. `{owner}_uuid`). Pass `local_key=` / `owner_key=` to override. Pivot
(`BelongsToMany`) and polymorphic (`MorphOne` / `MorphMany`) relations resolve
the owner's PK the same way, so attach/detach/sync and morph creates work on
non-`id` owners too.

## Belongs to (inverse)

```python
from arvel.database import BelongsTo, Model


class Post(Model):
    def author(self) -> BelongsTo["User"]:
        return self.belongs_to(User, foreign_key="author_id")
```

```python
author = await post.author().first()

# Associate / dissociate without persisting
await post.author().associate(user)
await post.author().dissociate()
await post.save()
```

`associate` sets `post.author_id = user.id` in memory. Call `save()` yourself.

## Many to many

`BelongsToMany` is a **class-level descriptor**. Define the pivot `Table` once and reference it from both sides:

```python
from sqlalchemy import Column, ForeignKey, Integer, Table

from arvel.database import BelongsToMany, Model
from arvel.database.orm import mapped_column

# define the join table (once, typically in a separate tables.py or alongside the model)
post_tags = Table(
    "post_tags",
    Model.metadata,
    Column("post_id", Integer, ForeignKey("posts.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
)


class Post(Model):
    tags: BelongsToMany["Tag"] = BelongsToMany(
        "Tag",  # or the Tag class directly, once it's defined
        table=post_tags,
        foreign_key="post_id",
        related_foreign_key="tag_id",
    )


class Tag(Model):
    posts: BelongsToMany["Post"] = BelongsToMany(
        "Post",
        table=post_tags,
        foreign_key="tag_id",
        related_foreign_key="post_id",
    )
```

Accessing `post.tags` on an instance returns a `BelongsToManyAccessor`:

```python
# iterate
async for tag in post.tags:
    print(tag.name)

# pivot operations
await post.tags.attach(tag.id, tagged_at="2026-05-30")   # pivot columns via kwargs
await post.tags.detach(tag.id)
await post.tags.update_pivot(tag.id, {"tagged_at": "..."})  # update existing pivot row

# sync — make the set exactly this list. Returns what changed.
changed = await post.tags.sync([tag1.id, tag2.id])
# changed == {"attached": [...], "detached": [...], "updated": [...]}

# sync with pivot data: {id: {pivot_col: value}}
await post.tags.sync({tag1.id: {"tagged_at": "2026-05-30"}})

await post.tags.sync_without_detaching([tag3.id])  # add/update only, never remove

# pivot row inspection
row = await post.tags.pivot(tag.id)           # dict | None
rows = await post.tags.where_pivot("role", "editor")

# toggle (attach if absent, detach if present)
result = await post.tags.toggle(tag.id)       # "attached" | "detached"
```

`sync` is the "make the set exactly this list" operation — it detaches IDs no longer in the list and attaches new ones in one transaction. It returns a `{"attached", "detached", "updated"}` dict, like Eloquent. Pass `{id: {pivot_col: value}}` instead of a plain list to set or update pivot columns; an ID already attached with different pivot data lands in `updated`.

## Polymorphic relations

Use `MorphOne` or `MorphMany` when several models share the same child table.

```python
from arvel.database import MorphMany, MorphOne, Model
from arvel.database.orm import mapped_column
from arvel.database import Mapped


class Image(Model):
    __tablename__ = "images"

    imageable_type: Mapped[str] = mapped_column(String(100))
    imageable_id: Mapped[int] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(String(500))


class Post(Model):
    image: MorphOne["Image"] = MorphOne(Image, name="imageable")


class Product(Model):
    image: MorphOne["Image"] = MorphOne(Image, name="imageable")
```

`MorphOne` returns an awaitable accessor:

```python
img = await post.image           # None if not set
img = await post.image.query()   # explicit async call

# create with discriminator columns set automatically
img = await post.image.create(url="https://example.com/pic.jpg")
```

`MorphMany` works the same way but returns multiple rows:

```python
class Comment(Model):
    __tablename__ = "comments"

    commentable_type: Mapped[str] = mapped_column(String(100))
    commentable_id: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)


class Post(Model):
    comments: MorphMany["Comment"] = MorphMany(Comment, name="commentable")


# accessing the accessor
all_comments = await post.comments.all()
new_comment = await post.comments.create(body="great post")
```

The type column stores the unqualified class name (`"Post"`, not `"app.models.Post"`).

Migration:

```python
def up(self, t: Blueprint) -> None:
    t.id()
    t.text("body")
    t.morphs("commentable")    # commentable_id (INTEGER) + commentable_type (VARCHAR)
    t.timestamps()
```

## Has many through

Reach a distant model through an intermediate one:

```python
from arvel.database import HasManyThrough, Model


class Country(Model):
    @classmethod
    def posts(cls) -> HasManyThrough["Post"]:
        return cls.has_many_through(Post, through=User)
```

`Country.posts()` builds a single SQL JOIN: `countries → users → posts`.

## Eager loading

Load relations alongside the parent query with `with_()` to avoid N+1. **This only works with descriptor-style relations** (`has_many_attr`, `BelongsToMany`, `MorphOne`, `MorphMany`).

```python
users = await User.with_("posts").all()

for user in users:
    print(user.posts)    # loaded, no extra query
```

Nested relations use dot notation:

```python
posts = await Post.with_("author", "comments").all()
```

Constrained eager loading — pass a callback to filter what gets loaded:

```python
users = await User.with_(
    {"posts": lambda q: q.where(Post.status == "published").order_by("-created_at")}
).all()
```

Mix constrained and unconstrained in one call:

```python
users = await User.with_(
    {"posts": lambda q: q.where(Post.status == "published")},
    "profile",
).all()
```

Each callback receives a `QueryBuilder` scoped to the related model and must return it.

## Querying through relations

`where_has`, `doesnt_have`, and `has` work with both descriptor-style attributes and `BelongsToMany` pivot descriptors:

```python
# At least one matching related row
users = await User.where_has(User.posts).all()

# Constrained existence check
users = await User.where_has(
    User.posts, lambda q: q.where(Post.status == "published")
).all()

# No related rows
users = await User.doesnt_have(User.posts).all()

# Count-based — at least 5
users = await User.has(User.posts, ">=", 5).all()

# BelongsToMany pivot
posts = await Post.where_has(Post.tags).all()
posts = await Post.where_has(
    Post.tags, lambda q: q.where_pivot("is_featured", True)
).all()
```

`has()` accepts `">"`, `">="`, `"<"`, `"<="`, `"="`, `"!="`. Default is `">= 1`.

## Aggregating over relations

```python
# Post count per user (adds .posts_count attribute)
users = await User.with_count("posts").all()
for user in users:
    print(user.name, user.posts_count)

# Sum of order totals per user
users = await User.with_sum("orders", "total_cents").all()
for user in users:
    print(user.name, user.orders_sum_total_cents)

# Maximum order value per user
users = await User.with_max("orders", "total_cents").all()
```

Attribute name pattern: `{relation}_{aggregate}_{column}` — `posts_count`, `orders_sum_total_cents`, `orders_max_total_cents`.

These only work with descriptor-style relations.

`with_count` accepts both SQLA relationships and `BelongsToMany` descriptors, and raises `UnknownRelationError` if the name isn't a relation on the model. `with_sum`/`with_max` cover SQLA relationships.

### Soft-deletes and relation counts

`has`, `where_has`, `doesnt_have`, and `with_count` honour the related model's soft-delete scope — trashed related rows are never counted or matched. A blog whose only comment has been soft-deleted has zero comments for `has("comments")` and `with_count("comments")`, just like Eloquent.

## N+1 prevention

The attribute style (`has_many_attr`, `BelongsToMany`, `MorphOne`, `MorphMany`) enforces `lazy="raise_on_sql"`. Accessing a relation without loading it raises `sqlalchemy.exc.InvalidRequestError` immediately — the N+1 bug is visible at the line that caused it:

```python
# Fine — loaded
users = await User.with_("posts").all()
_ = users[0].posts    # no error

# Raises — not loaded
user = await User.find(1)
_ = user.posts        # InvalidRequestError: 'User.posts' is not available due to lazy='raise_on_sql'
```

Method-style relations don't have this guard because they're not attributes — you always call them explicitly:

```python
posts = await user.posts().get()    # always explicit, no silent query
```

### Testing for N+1

Use `QueryLog.assert_max_queries` to verify a code path issues at most N queries:

```python
from arvel.database.query_logging import QueryLog


async def test_list_users_no_n_plus_one() -> None:
    await User.factory().create_many(10)

    with QueryLog.assert_max_queries(2):
        users = await User.with_("posts").all()
        for user in users:
            _ = user.posts    # must not query
```

The context manager raises `AssertionError` if the actual query count exceeds the limit.

## Where to next?

- [Arvent: Getting Started](arvent.md) — defining models and basic queries.
- [Collections](arvent-collections.md) — what relations return.
- [Migrations](migrations.md) — schema setup including `t.morphs(...)`.
- [Database Testing](database-testing.md) — keeping tests clean and fast.
