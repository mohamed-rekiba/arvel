# Relationships

<a name="introduction"></a>
## Introduction

Database tables are often related to one another. A blog post may have many comments, or an order could be related to the user who placed it. Arvent makes managing and working with these relationships easy, and supports the common relationship types: one-to-one, one-to-many, many-to-many, polymorphic, through, and recursive (tree) relationships.

In Arvent, a relationship is declared as a **zero-argument method** that returns a relationship builder. The framework detects these methods, wires them for querying, and makes them eager-loadable.

<a name="defining-relationships"></a>
## Defining Relationships

<a name="one-to-many"></a>
### One to Many

A one-to-many relationship is used to define relationships where a single model is the parent to one or more child models. For example, a user may have many posts:

```python
from arvel.database import Model, Timestamps, foreign_id, id_, string


class User(Model, Timestamps):
    __tablename__ = "users"
    id: int = id_()
    name: str = string(120)

    def posts(self):
        return self.has_many(Post)
```

<a name="one-to-one"></a>
### One to One

A one-to-one relationship links exactly one related row, such as a user's profile:

```python
class User(Model, Timestamps):
    __tablename__ = "users"
    id: int = id_()

    def profile(self):
        return self.has_one(Profile)
```

<a name="belongs-to"></a>
### The Inverse: Belongs To

Define the inverse with `belongs_to`. A post belongs to its author:

```python
class Post(Model, Timestamps):
    __tablename__ = "posts"
    id: int = id_()
    user_id: int = foreign_id("users.id")
    title: str = string(200)

    def author(self):
        return self.belongs_to(User)
```

<a name="custom-keys"></a>
### Custom Keys

Arvent assumes the foreign key follows the `{parent}_id` convention and the local key is the parent's primary key. Override either when your schema differs:

```python
def posts(self):
    return self.has_many(Post, foreign_key="author_id", local_key="id")


def author(self):
    return self.belongs_to(User, foreign_key="author_id", owner_key="id")
```

<a name="has-one-of-many"></a>
### Has One of Many

Sometimes a model has many related rows but you only want one of them — the *latest* order, the *highest* bid, the *oldest* membership. Calling the `has_many` relation gives you helpers that pick a single row by aggregating a column:

```python
class User(Model, Timestamps):
    __tablename__ = "users"
    id: int = id_()

    def orders(self):
        return self.has_many(Order)


latest = await user.orders().latest_of_many()           # MAX(created_at)
first = await user.orders().oldest_of_many()            # MIN(created_at)
priciest = await user.orders().of_many("total", "max")  # MAX of any column
```

These run a one-row query each time, so for a list of users they'd be N+1. When you need to eager-load "one of many" across many parents in a single query, declare a `HasOneOfMany` **descriptor** instead:

```python
from typing import ClassVar
from arvel.database.orm.has_one_of_many import HasOneOfMany


class User(Model, Timestamps):
    __tablename__ = "users"
    id: int = id_()

    latest_order: ClassVar[HasOneOfMany["Order"]] = HasOneOfMany(
        Order, column="created_at", aggregate="max"
    )


users = await User.with_("latest_order").get()
order = await user.latest_order      # awaitable accessor; served from cache after with_()
```

The descriptor eager-loads with a single grouped subquery (`MAX(created_at) … GROUP BY user_id`) rather than one query per user. Ties on the aggregate column are broken by the larger primary key, so the result is deterministic.

<a name="querying-relationships"></a>
## Querying Relationships

Because a relationship method returns a query builder, you can add constraints before running it. Call the method, chain query methods, then await a terminal:

```python
recent = await (
    user.posts()
    .where(is_published=True)
    .order_by("-created_at")
    .get()
)
```

<a name="relationship-write-helpers"></a>
### Relationship Write Helpers

Relationship builders add write helpers that set the foreign key for you.

`has_many` and `has_one` provide `save`, `create`, `save_many`, and `create_many`. Note that `create` takes a **dict** of attributes:

```python
post = await user.posts().create({"title": "Hello"})
await user.posts().save_many([post_a, post_b])
```

`belongs_to` provides `associate`, `dissociate`, and `with_default`:

```python
await post.author().associate(other_user)   # sets post.user_id
await post.author().dissociate()            # clears it
```

`with_default(...)` returns a placeholder model instead of `None` when no parent exists — handy for avoiding null checks in templates and resources.

<a name="many-to-many"></a>
## Many to Many

Many-to-many relationships are slightly more involved — they use a pivot (join) table. Declare a `BelongsToMany` **descriptor** as a class attribute, pointing at the related model and the pivot table:

```python
from typing import ClassVar
from sqlalchemy import Column, ForeignKey, Integer, Table
from arvel.database import Model, Timestamps, id_, string
from arvel.database.orm.belongs_to_many import BelongsToMany


# The pivot is a SQLAlchemy Table on the shared Model.metadata.
post_tag_table = Table(
    "post_tag",
    Model.metadata,
    Column("post_id", Integer, ForeignKey("posts.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
)


class Tag(Model):
    __tablename__ = "tags"
    id: int = id_()
    name: str = string(50)


class Post(Model, Timestamps):
    __tablename__ = "posts"
    id: int = id_()

    tags: ClassVar[BelongsToMany[Tag]] = BelongsToMany(
        Tag,
        table=post_tag_table,
        foreign_key="post_id",
        related_foreign_key="tag_id",
    )
```

Read the related rows by awaiting the accessor's `all()`, or iterate it directly:

```python
tags = await post.tags.all()

async for tag in post.tags:
    print(tag.name)
```

<a name="managing-the-pivot"></a>
### Managing the Pivot

The accessor exposes pivot management methods:

```python
await post.tags.attach(tag_id)
await post.tags.detach(tag_id)
await post.tags.sync([1, 2, 3])               # exact set; detaches the rest
await post.tags.sync_without_detaching([4])   # add without removing
await post.tags.toggle(5)                     # attach if absent, detach if present
await post.tags.create(name="python")         # create related + attach
```

> [!NOTE]
> `create(...)` takes the related model's attributes as keyword arguments. A lone positional dict binds to the `pivot` parameter, not the attributes.

<a name="pivot-columns"></a>
### Pivot Columns

When the pivot table carries extra columns, pass them when attaching and filter by them when querying:

```python
await post.tags.attach(tag_id, added_by="system")

featured = await post.tags.where_pivot("added_by", "editor")
ordered = await post.tags.order_by_pivot("created_at")
```

Pivot data is passed as keyword arguments to `attach`. `where_pivot` and `order_by_pivot` are `async` and return the list of related models directly — there's no `.all()` to chain.

> [!WARNING]
> Pivot filters like `where_pivot` live on the `BelongsToMany` accessor only. Calling `where_pivot` on a plain query builder raises `RuntimeError`.

<a name="polymorphic-relationships"></a>
## Polymorphic Relationships

A polymorphic relationship lets a model belong to more than one other model type on a single association. The classic example: comments that can attach to posts *and* videos.

| Class | Role |
|---|---|
| `MorphOne(Related, name=...)` | One-to-one polymorphic |
| `MorphMany(Related, name=...)` | One-to-many polymorphic |
| `MorphTo(name=...)` | The inverse — resolves the parent |
| `MorphToMany(Related, table=, name=, related_key=)` | Many-to-many polymorphic |
| `MorphedByMany(...)` | The inverse of `MorphToMany` |

```python
from arvel.database.orm.morph import MorphMany, MorphTo


class Post(Model):
    __tablename__ = "posts"
    id: int = id_()
    comments: ClassVar[MorphMany["Comment"]] = MorphMany(Comment, name="commentable")


class Comment(Model):
    __tablename__ = "comments"
    id: int = id_()
    commentable: ClassVar[MorphTo] = MorphTo(name="commentable")
```

The relationship stores two columns — `{name}_type` and `{name}_id`. Access them by awaiting:

```python
comments = await post.comments.all()
parent = await comment.commentable    # the Post or Video it belongs to
```

<a name="the-morph-map"></a>
### The Morph Map

By default the type column stores the model's class name. Register a **morph map** to store stable aliases instead, so renaming a class doesn't orphan existing rows:

```python
from arvel.database import morph_map

morph_map({"post": Post, "video": Video})
```

> [!NOTE]
> A partial morph map is fine: unmapped types fall back to the short class name. Call `require_morph_map()` to turn on strict mode, where an unmapped type raises `MorphMapError` instead of falling back.

<a name="morph-class-override"></a>
### Overriding the Morph Class

Every model resolves its polymorphic type token through `get_morph_class()` — Laravel's `getMorphClass()`. By default that's the morph-map alias, else the short class name. Set `__morph_class__` to override it model-wide. A read-only view model uses this to present as the canonical model, so it shares the same polymorphic rows — every `MorphOne`/`MorphMany`/`MorphToMany` on it, plus `.with_(...)` eager loads and the accessors, target the canonical type:

```python
class ProductCatalog(Model):  # a read-only view of products
    __morph_class__ = "Product"  # share Product's polymorphic rows
```

Now `ProductCatalog.get_morph_class()` returns `"Product"`, and `ProductCatalog.with_("media")` loads the rows stored under `"Product"` — no `"ProductCatalog"` rows ever exist.

<a name="through-relationships"></a>
## Through Relationships

A "through" relationship reaches a distant relation via an intermediate model — for example, a country has many posts *through* users. Declare these as class methods:

```python
class Country(Model):
    __tablename__ = "countries"
    id: int = id_()

    @classmethod
    def posts(cls):
        return cls.has_many_through(Post, User)
```

```python
posts = await Country.has_many_through(Post, User).where(...).get()
```

`has_one_through` is the single-result variant.

<a name="recursive-relationships"></a>
## Recursive Relationships

For self-referential trees (categories, comments, org charts), use the recursive relationships, which walk an adjacency list via a recursive CTE:

```python
class Category(Model):
    __tablename__ = "categories"
    id: int = id_()
    parent_id: int | None = foreign_id("categories.id", nullable=True)

    def descendants(self):
        return self.has_many_recursive(parent_key="parent_id")

    def ancestors(self):
        return self.belongs_to_recursive(parent_key="parent_id")
```

```python
tree = await category.descendants().with_max_depth(5).all()
nodes = await category.descendants().as_tree()   # nested TreeNode structure
```

Eager-load a whole tree with `with_tree(...)`:

```python
roots = await Category.where_null("parent_id").with_tree("descendants", max_depth=5).get()
for root in roots:
    forest = await root.descendants().as_tree()   # served from cache, no re-query
```

<a name="eager-loading"></a>
## Eager Loading

Accessing a relationship per row causes the **N+1 query problem** — one query for the parents, then one more for each parent's relation. Eager loading fetches everything up front. Use `with_` (note the trailing underscore — `with` is a Python keyword):

```python
users = await User.with_("posts").get()

for user in users:
    await user.posts.all()   # already loaded; no extra query
```

Nested relations use dot notation:

```python
await User.with_("posts.comments").get()
```

> [!NOTE]
> Arvel's eager-load method is `with_`, not `with`. There is no `with` alias — Python reserves the keyword.

<a name="constrained-eager-loading"></a>
### Constrained Eager Loading

To constrain the rows that are eager-loaded, pass a mapping of relation name to a closure that modifies the relation's query:

```python
users = await User.with_({
    "posts": lambda q: q.where(Post.published == True),
}).get()
```

<a name="selecting-and-dropping-eager-loads"></a>
### Selecting & Dropping Eager Loads

`with_only` replaces any pending eager loads with exactly the relations you name — handy when a base query or scope already adds some you don't want here. `without` drops named relations from the pending set:

```python
base = User.with_("posts", "profile", "roles")

await base.with_only("posts").get()   # only posts is loaded
await base.without("roles").get()     # posts + profile, no roles
```

<a name="hydrating-the-inverse"></a>
### Hydrating the Inverse

When you eager-load children and then walk back to the parent from each child, that back-reference is another N+1. `chaperone()` — used inside a `with_` closure — hydrates each child's inverse parent with the already-loaded instance, so `comment.post` returns the in-memory post without a query:

```python
posts = await Post.with_({"comments": lambda q: q.chaperone()}).get()
# now comment.post is the same Post object, no extra query
```

<a name="lazy-eager-loading"></a>
### Lazy Eager Loading

When you already have the parent models, load relations onto them after the fact:

```python
await user.load("posts", "profile")
await user.load_missing("posts")     # only loads if not already loaded

# on a whole collection
await users.load("posts")
await users.load_missing("posts")
```

<a name="eager-loading-and-soft-deletes"></a>
### Eager Loading and Soft Deletes

Eager loads honour the **related** model's global scopes. If the related model uses soft deletes, `with_` skips trashed rows — the same behaviour as the lazy accessor, `with_count`, and `where_has`:

```python
# Comment uses SoftDeletes; trashed comments are left out
await Post.with_("comments").get()
```

To include trashed related rows, opt back in with a constraint closure:

```python
await Post.with_({"comments": lambda q: q.with_trashed()}).get()
```

<a name="counting-related-models"></a>
### Counting Related Models

To count related rows without loading them, use `with_count`. Other aggregates work the same way:

```python
users = await User.with_count("posts").get()
# each user now carries posts_count

await User.with_sum("orders", "total").get()
await User.with_avg("orders", "total").get()
await User.with_min("orders", "total").get()
await User.with_max("orders", "total").get()
await User.with_exists("posts").get()
```

You can alias the result with an `"as"` suffix, and load aggregates onto existing models with `load_count`, `load_sum`, and `load_exists`:

```python
await User.with_count("comments as total").get()
await user.load_count("posts")
```

<a name="querying-relationship-existence"></a>
## Querying Relationship Existence

To filter parents by whether they have related rows — without loading the relations — use `has`, `where_has`, and friends:

```python
# users that have at least one post
await User.has("posts").get()

# users with at least 3 published posts
await User.where_has(
    "posts",
    lambda q: q.where(Post.published == True),
    operator=">=",
    count=3,
).get()

# users with no posts
await User.doesnt_have("posts").get()

# nested existence
await User.where_has("posts.comments").get()
```

`where_relation` is sugar for a `where_has` with a single column constraint:

```python
await User.where_relation("posts", "status", "published").get()
```

To filter the children of a known parent, `where_belongs_to` takes the parent instance and scopes by its foreign key — no need to remember the column name:

```python
await Post.where_belongs_to(current_user).get()        # posts of this user
await Post.where_belongs_to(current_user, "author").get()   # name the relation explicitly
```

For polymorphic existence, use `where_has_morph` and `has_morph`. See the [query builder](query-builder.md) for the full filtering surface.
