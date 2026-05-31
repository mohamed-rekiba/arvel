# ORM Relationships

Tables are often related to each other — a post belongs to a user, a user has many posts, a post has many tags. Arvel ships first-class support for the common relation types, including polymorphic and many-to-many.

## How relations are declared

Foreign-key relations — **has many**, **has one**, and **belongs to** — are plain instance methods that return a relation builder. One declaration gives you everything: chainable lazy queries, writes, eager loading with `with_()`, existence checks with `where_has()`, and counts with `with_count()`. This mirrors Laravel, where `$user->posts()` is the query and `$user->posts` is the loaded collection.

```python
from arvel.database import Model
from arvel.database.orm.relations import HasMany


class User(Model):
    __tablename__ = "users"

    def posts(self) -> HasMany["Post"]:
        return self.has_many(Post)
```

Pivot and polymorphic relations — `BelongsToMany`, `MorphOne`, `MorphMany`, `MorphTo`, `MorphToMany`, `MorphedByMany`, `HasOneOfMany` — are class-level **descriptors**, since they carry pivot tables or discriminator columns that don't fit a single FK. They get their own sections below.

## Has many

A `has_many` method returns a `HasMany` builder. Call it (`user.posts()`) to get a `QueryBuilder` scoped to `WHERE user_id = user.id`, then chain and execute:

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

### Eager loading and existence queries

The same method-style relation is eager-loadable. Pass its name to `with_()`, `where_has()`, `has()`, `doesnt_have()`, and `with_count()`:

```python
# one query for users + one for posts — no N+1
users = await User.with_("posts").all()

for user in users:
    posts = await user.posts().get()   # served from the eager cache, no extra query
```

After `with_("posts")`, calling `user.posts().get()` reads from the per-instance eager cache instead of querying. Without eager loading it runs a normal scoped query — there's no silent N+1 because the call is always explicit.

```python
# Users who have at least one post
active = await User.where_has("posts").all()

# Users with no posts
empty = await User.doesnt_have("posts").all()

# Users with at least 5 posts
prolific = await User.has("posts", ">=", 5).all()

# Users with a post matching a condition
with_published = await User.where_has(
    "posts", lambda q: q.where(Post.status == "published")
).all()
```

Reference the relation by its string name (`"posts"`) — the method itself isn't a class attribute you can pass.

### Referencing a related model by name

`has_many`, `has_one`, and `belongs_to` accept either the related class or its name as a string. The string form sidesteps circular imports — no top-level import of the related model is needed, so two models that point at each other stay clean:

```python
class User(Model):
    def orders(self) -> HasMany["Order"]:
        return self.has_many("Order", foreign_key="user_id")
```

The name resolves against the mapper registry the first time the relation runs, so the target class only has to be imported *somewhere* before then — not in this module.

## Has one

```python
from arvel.database import Model
from arvel.database.orm.relations import HasOne


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

### Has one of many (latest / oldest)

Pick exactly one row out of a one-to-many — the latest or oldest by a column. Two forms:

**Method style** off `has_many`/`has_one` — lazy, per-instance:

```python
latest = await post.has_many(Comment).latest_of_many("created_at")
oldest = await post.has_many(Comment).oldest_of_many("created_at")
top    = await post.has_many(Comment).of_many("score", aggregate="max")
```

Each orders by the column (with the PK as a deterministic tiebreaker) and returns one row.

**Descriptor style** — eager-loadable over a list with a single grouped subquery:

```python
from typing import ClassVar

from arvel.database import Model
from arvel.database.orm import HasOneOfMany


class Post(Model):
    latest_comment: ClassVar[HasOneOfMany["Comment"]] = HasOneOfMany(
        Comment, column="created_at", aggregate="max"
    )


posts = await Post.with_("latest_comment").get()   # 1 query for posts + 1 subquery
for p in posts:
    one = await p.latest_comment                   # served from the eager cache
```

`with_("latest_comment")` runs one `SELECT fk, MAX(col) ... GROUP BY fk` joined back to the table, so
it fetches ~one row per parent instead of every related row. `foreign_key` defaults to
`{snake(owner)}_id`.

### Chaperone (inverse parent hydration)

When you eager-load a has-many and then walk back from each child to its parent, `chaperone()` sets the
inverse to the already-loaded parent — so the loop stays query-free and you get the *same* instance back:

```python
posts = await Post.with_({"comments": lambda q: q.chaperone()}).all()
for p in posts:
    for c in await p.comments().get():
        assert await c.post().first() is p     # the loaded post, no query
```

It composes with a filter — `lambda q: q.where(Comment.published == True).chaperone()` filters the
eager-loaded children and hydrates their inverse. The inverse is inferred from the child's `belongs_to`
back to the parent (or `back_populates` for SA relationships); pass it explicitly when it can't be
inferred: `q.chaperone("post")`.

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
from arvel.database import Model
from arvel.database.orm.relations import BelongsTo


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

### Default models

When the FK is null (or no row matches), `with_default` returns a placeholder instead of `None` — so templates and callers never hit a `None.name`:

```python
author = await post.author().with_default().first()                 # empty User instance
author = await post.author().with_default({"name": "Guest"}).first() # with attributes
author = await post.author().with_default(
    lambda user, post: setattr(user, "name", f"author-of-{post.title}")
).first()
```

A real matched parent always wins over the default.

## Touching parents

List parent relation methods in `__touches__` to bump their `updated_at` whenever the child is saved:

```python
class Comment(Model):
    __touches__ = ("post",)

    def post(self) -> BelongsTo["Post"]:
        return self.belongs_to(Post)
```

Saving a comment now also touches its post — handy for cache invalidation keyed on the parent.

## Cascade save with push

`save()` persists one model. `push()` saves the model **and** every loaded relation (recursively), so edits made across an eager-loaded graph go down in one call:

```python
user = await User.with_("posts").first()
user.name = "renamed"
posts = await user.posts().get()
posts[0].title = "edited"
await user.push()   # saves the user and the edited post
```

## Many to many

`BelongsToMany` is a **class-level descriptor**. Define the pivot `Table` once and reference it from both sides:

```python
from sqlalchemy import Column, ForeignKey, Integer, Table

from arvel.database import Model
from arvel.database.orm import BelongsToMany

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

### Pivot ergonomics

Configure the relation at class definition with fluent builders, mirroring Eloquent's `withPivot`/`withTimestamps`/`as`:

```python
class Post(Model):
    tags: BelongsToMany["Tag"] = (
        BelongsToMany("Tag", table=post_tags, foreign_key="post_id", related_foreign_key="tag_id")
        .with_pivot("role", "priority")   # surface extra pivot columns
        .with_timestamps()                # maintain pivot created_at / updated_at
        .as_("membership")                # name the pivot accessor (default: "pivot")
    )
```

`with_pivot` hydrates those columns onto each related row under the accessor name:

```python
for tag in await post.tags.all():
    print(tag.membership.role, tag.membership.priority)
```

`with_timestamps` sets the pivot `created_at`/`updated_at` on `attach`/`sync`, and bumps `updated_at` on `update_pivot`. Filter and order by pivot columns, and persist-and-attach in one call:

```python
# ordering
await post.tags.order_by_pivot("priority")           # asc
await post.tags.order_by_pivot("priority", "desc")

# filters (each returns the related rows)
await post.tags.where_pivot_in("role", ["admin", "editor"])
await post.tags.where_pivot_not_in("role", ["viewer"])
await post.tags.where_pivot_between("priority", 1, 5)
await post.tags.where_pivot_null("role")             # negate=True for NOT NULL

# create / save through the relation
tag = await post.tags.create(pivot={"role": "owner"}, name="ops")
await post.tags.save(existing_tag, pivot={"priority": 7})
```

## Polymorphic relations

Use `MorphOne` or `MorphMany` when several models share the same child table.

```python
from arvel.database import Model, integer, string, text
from arvel.database.orm import MorphMany, MorphOne


class Image(Model):
    __tablename__ = "images"

    imageable_type: str = string(100)
    imageable_id: int = integer(index=True)
    url: str = string(500)


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

    commentable_type: str = string(100)
    commentable_id: int = integer(index=True)
    body: str = text()


class Post(Model):
    comments: MorphMany["Comment"] = MorphMany(Comment, name="commentable")


# accessing the accessor
all_comments = await post.comments.all()
new_comment = await post.comments.create(body="great post")
```

The type column stores the unqualified class name (`"Post"`, not `"app.models.Post"`) — unless a
[morph map](#morph-map) assigns an alias.

`MorphOne`/`MorphMany` are full query relations. They batch-load with `with_()`, filter with
`where_has`/`has`/`doesnt_have`, count with `with_count`, and lazy-load onto an existing instance
with `Model.load()`:

```python
posts = await Post.with_("comments").with_count("comments").get()
for p in posts:
    p.comments_count                     # count column
    for c in await p.comments.all():     # served from the eager cache, no N+1
        ...

# Only posts that have at least one comment containing "hello":
await Post.where_has("comments", lambda q: q.where(Comment.body.like("%hello%"))).get()

# Lazy-load onto an already-fetched post:
await post.load("comments")
```

Migration:

```python
def up(self, t: Blueprint) -> None:
    t.id()
    t.text("body")
    t.morphs("commentable")    # commentable_id (INTEGER) + commentable_type (VARCHAR)
    t.timestamps()
```

### Morph map

By default the `{name}_type` column stores the owner's **short class name** (`"Post"`). That token
breaks if you rename or move the class. Register a morph map at boot to pin stable aliases instead:

```python
from arvel.database import morph_map, require_morph_map

morph_map({"post": Post, "video": Video})
```

Now polymorphic writes store `"post"` / `"video"`, and `Post.get_morph_class()` returns `"post"`.
Unmapped models keep storing the short name, so adopting a map is incremental.

To enforce that *every* polymorphic model has an alias — turning an accidental unmapped write into a
loud error — flip strict mode:

```python
require_morph_map()   # unmapped polymorphic use now raises MorphMapError
```

If you adopt aliases for an existing app, backfill the old class-name tokens to the new aliases in a
one-off migration before enabling the map.

### MorphTo — the inverse side

`MorphTo` is the child's view of its polymorphic parent. The child stores `{name}_type` +
`{name}_id`; `MorphTo` resolves them back to the parent model:

```python
from typing import Any, ClassVar

from arvel.database import Model, integer, string
from arvel.database.orm import MorphTo

class Comment(Model):
    commentable_type: str | None = string(60, nullable=True, default=None)
    commentable_id: int | None = integer(nullable=True, default=None)

    commentable: ClassVar[MorphTo[Any]] = MorphTo(name="commentable")
```

```python
parent = await comment.commentable          # a Post or a Video, resolved from the token
```

Point a comment at a parent — or detach it — with `associate` / `dissociate`. Both set or clear the
type and id columns together; save the child to persist:

```python
comment.commentable.associate(post)         # sets commentable_type + commentable_id
await comment.save()

comment.commentable.dissociate()            # nulls both columns
await comment.save()
```

Eager-load the parent across a list of children with `with_()`. Parents are batched **one query per
distinct type**, so iterating and accessing `comment.commentable` never triggers N+1:

```python
comments = await Comment.with_("commentable").get()
for c in comments:
    parent = await c.commentable             # served from cache, no query
```

A `morphTo` is a leaf in eager paths — its parent type varies per row, so nested paths through it
(`commentable.author`) aren't supported.

#### Filtering across morph types

`MorphTo` has no single related table, so plain `where_has` can't reach it. Use `where_has_morph` to
filter against one or more concrete target types — it OR's a per-type `EXISTS` subquery:

```python
# Comments attached to a Post or a Video
await Comment.query().where_has_morph("commentable", [Post, Video]).get()

# With a per-type constraint — the closure gets (query, type_model)
await Comment.query().where_has_morph(
    "commentable", [Post], lambda q, _type: q.where(Post.published == True)
).get()
```

It honours a registered `morph_map`, so the stored token (`"post"`) is what gets matched.
`has_morph(relation, types, operator, count)` is the count-based form, and `where_morph_relation(
relation, types, column, value)` is sugar for "the morphed parent has `column == value`".

## MorphToMany

`MorphToMany` is a **polymorphic many-to-many**: like `BelongsToMany`, but the pivot carries a `{name}_type` / `{name}_id` discriminator pair instead of a single owner foreign key. One pivot table can therefore link several owner types to the same related model — this is exactly how [`arvel-permission`](permission.md) lets both a `User` and a `Team` share the `model_has_roles` pivot.

Declare it as a `ClassVar` descriptor, pointing at a shared pivot `Table`:

```python
from typing import ClassVar

from arvel.database import Model
from arvel.database.orm import MorphToMany
from sqlalchemy import Column, ForeignKey, String, Table

# A pivot keyed by (model_type, model_id, role_id)
model_has_roles = Table(
    "model_has_roles",
    Model.metadata,
    Column("model_type", String(255), primary_key=True),
    Column("model_id", String(36), primary_key=True),
    Column("role_id", ForeignKey("roles.id"), primary_key=True),
)


class User(Model):
    roles: ClassVar[MorphToMany["Role"]] = MorphToMany(
        Role, table=model_has_roles, name="model", related_key="role_id"
    )
```

`name="model"` selects the `model_type` / `model_id` column pair. The `model_type` value is the owner's short class name (`"User"`), and `model_id` is the **string-cast owner PK** — written and compared as a string so a `VARCHAR` pivot column accepts integer, UUID, and string primary keys without a dialect-specific cast.

Accessing the attribute on an instance returns a `MorphToManyAccessor`:

```python
await user.roles.attach(role.id)        # True if new, False if already attached
await user.roles.detach(role.id)        # no-op if absent
await user.roles.toggle(role.id)        # "attached" or "detached"
await user.roles.sync([1, 2, 3])        # replace the set, returns {attached, detached, updated}
await user.roles.sync_without_detaching([4])
rows = await user.roles.all()           # list[Role]
row = await user.roles.pivot(role.id)   # the pivot row as a dict, or None
matches = await user.roles.where_pivot("expires_at", None)
async for role in user.roles:           # streaming iteration
    ...
```

Every INSERT/SELECT/DELETE sets both discriminator columns, so there's no `model_type`-NULL bug class and no separate `save()` step.

`MorphToMany` is a full query relation: `with_("roles")` batch-loads it (N+1-free), and `where_has`
/ `with_count` build the right EXISTS / COUNT subqueries with the morph predicate (see below).

### MorphedByMany — the inverse side

`MorphedByMany` is the other end of a `MorphToMany`, declared on the model the pivot's
`{name}_type`/`{name}_id` point at. One `taggables` pivot links many owner types to one tag, so the
tag can look back at each type with its own relation. Mirrors Laravel's `morphedByMany`.

```python
from arvel.database.orm import MorphedByMany, MorphToMany


class Tag(Model):
    # `related_key` is the pivot column holding the tag's own PK. The related
    # model is referenced lazily because it's defined later in the module.
    posts: ClassVar[MorphedByMany["Post"]] = MorphedByMany(
        lambda: Post, table=taggables, name="taggable", related_key="tag_id"
    )
    videos: ClassVar[MorphedByMany["Video"]] = MorphedByMany(
        lambda: Video, table=taggables, name="taggable", related_key="tag_id"
    )


class Post(Model):
    tags: ClassVar[MorphToMany["Tag"]] = MorphToMany(
        Tag, table=taggables, name="taggable", related_key="tag_id"
    )
```

The inverse accessor pins the discriminator to the *related* model's alias (`taggable_type == "Post"`)
and joins `taggable_id` back to the related PK, so `tag.posts` never bleeds into `tag.videos`:

```python
await tag.posts.attach(post.id)         # idempotent; sets tag_id + taggable_type + taggable_id
await tag.posts.detach(post.id)
await tag.posts.toggle(post.id)
await tag.posts.sync([1, 2, 3])
posts = await tag.posts.all()           # list[Post] — only Posts, not Videos

# Query-integrated, same as the forward side:
tags = await Tag.with_("posts").with_count("posts").get()   # batched, N+1-free
await Tag.where_has("posts").get()
```

## Has many through

Reach a distant model through an intermediate one:

```python
from arvel.database import Model
from arvel.database.orm.relations import HasManyThrough


class Country(Model):
    @classmethod
    def posts(cls) -> HasManyThrough["Post"]:
        return cls.has_many_through(Post, through=User)
```

`Country.posts()` builds a single SQL JOIN: `countries → users → posts`.

## Recursive relations (trees)

When a model points at itself with a `parent_id`, you've got an adjacency-list tree. Declare `descendants` (walk down) and `ancestors` (walk up) the same way you declare any other relation — zero-arg accessors:

```python
from typing import Self

from arvel.database import Model, foreign_id, id_, relationship, string
from arvel.database.orm.relations import Ancestors, Descendants


class Category(Model):
    id: int = id_()
    name: str = string(120)
    parent_id: int | None = foreign_id("categories.id", nullable=True)
    # The tree edge. `with_tree("descendants")` hydrates this in memory so you can
    # walk `node.children` synchronously — see "Eager loading" below.
    children: list[Category] = relationship(default_factory=list)

    def descendants(self) -> Descendants[Self]:
        return self.has_many_recursive(parent_key="parent_id")

    def ancestors(self) -> Ancestors[Self]:
        return self.belongs_to_recursive(parent_key="parent_id")
```

`parent_key` defaults to `"parent_id"`, so for the common case you can call `self.has_many_recursive()` with no arguments. The `children` relation is optional — declare it only when you want to walk the loaded tree node-by-node (the next section).

### Lazy read-back

Each accessor runs one recursive CTE. `.get()` returns the flat subtree; `.as_tree()` returns a `TreeNode` forest assembled in-memory (zero extra queries):

```python
category = await Category.find(1)

flat = await category.descendants().get()        # ModelCollection[Category]
tree = await category.descendants().as_tree()    # list[TreeNode[Category]]

for node in tree:                                 # direct children at depth 0
    print(node.node.name, node.depth)
    for child in node.children:                   # grandchildren at depth 1, ...
        print("  ", child.node.name)

trail = await category.ancestors().get()          # root → ... → parent
```

A `TreeNode` carries the model (`node`), its `depth` (roots at 0), and `children`.

### Filtering and capping the walk

Chain `.where(...)` to filter every level — pruning a node prunes its whole branch — and `.with_max_depth(n)` to cap the number of hops:

```python
visible = await category.descendants().where(Category.status == "visible").get()
direct = await category.descendants().with_max_depth(1).get()   # children only
```

### Eager loading with `with_tree()`

Loading descendants for a whole result set lazily is N+1. `with_tree()` loads the entire subtree for every parent in **one** query (a single CTE seeded by all parent ids) and wires it up as a navigable tree. When the model declares a `children` relation, you walk it synchronously — no `await`, no `as_tree()`, just plain models:

```python
roots = await (
    Category.where(Category.parent_id.is_(None))
    .with_tree("descendants")
    .get()
)

for root in roots:
    for child in root.children:          # direct children, already loaded
        for grandchild in child.children:  # and so on, all depths — no query
            ...
```

Every node in the loaded subtree has its `children` populated; a leaf's `children` is an empty list, never a lazy load. If you'd rather have depth metadata, `await root.descendants().as_tree()` still serves a `TreeNode` forest from the same cache with no extra query.

`with_tree()` takes the same knobs as the lazy walk:

```python
await (
    Category.with_tree(
        "descendants",
        constraint=lambda q: q.where(Category.status == "visible"),
        max_depth=3,
    )
    .get()
)
```

Both `constraint` and `max_depth` are optional. Passing a recursive relation to plain `with_()` works too and loads it with defaults.

!!! note "Acyclic data"
    The walk assumes the tree is acyclic. If a row can become its own ancestor, set `max_depth` to bound the recursion. With `max_depth` (or a pruning `constraint`), nodes at the boundary report `children == []` because their children weren't loaded. `where_has` / `with_count` over a recursive relation aren't supported — use `with_tree()` to load it, then inspect the loaded subtree. Synchronous `children` walking is for `descendants`; `ancestors` reads back via `.get()` / `.as_tree()`.

## Eager loading

Load relations alongside the parent query with `with_()` to avoid N+1. It works with every relation — the method-style FK relations (`has_many` / `has_one` / `belongs_to`) and the pivot/polymorphic descriptors (`BelongsToMany`, `MorphOne`, `MorphMany`, `MorphToMany`).

```python
users = await User.with_("posts").all()

for user in users:
    posts = await user.posts().get()    # served from the eager cache, no extra query
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

### Editing the eager-load set

Eager loads are deferred until the query runs, so you can edit the set after `with_()`:

```python
# Drop a relation a base query or scope added
users = await User.with_("posts", "profile").without("posts").get()

# Replace whatever was queued with exactly these
users = await User.with_("posts").with_only("profile").get()
```

`without(*names)` removes queued loads by name; `with_only(*relations)` clears the queue and registers only what you pass.

## Querying through relations

`where_has`, `doesnt_have`, and `has` work with the method-style FK relations and every pivot descriptor (`BelongsToMany`, `MorphToMany`, `MorphedByMany`). Reference each relation by its string name:

```python
# At least one matching related row
users = await User.where_has("posts").all()

# Constrained existence check
users = await User.where_has(
    "posts", lambda q: q.where(Post.status == "published")
).all()

# No related rows
users = await User.doesnt_have("posts").all()

# Count-based — at least 5
users = await User.has("posts", ">=", 5).all()

# BelongsToMany pivot
posts = await Post.where_has("tags").all()
posts = await Post.where_has(
    "tags", lambda q: q.where_pivot("is_featured", True)
).all()
```

`has()` accepts `">"`, `">="`, `"<"`, `"<="`, `"="`, `"!="`. Default is `">= 1`.

### Nested paths, counts, and OR branches

`where_has` walks relation chains and takes an operator/count, so you can filter on a relation of a relation or require a threshold:

```python
# Users who have at least one post that has at least one comment
users = await User.where_has("posts.comments").get()

# Posts with 3 or more comments
posts = await Post.where_has("comments", None, ">=", 3).get()

# Posts with 2+ non-spam comments (constraint applies at the leaf hop)
posts = await Post.where_has(
    "comments", lambda q: q.where(Comment.spam == False), ">=", 2
).get()
```

A constrained `doesnt_have` means "no related row matching the constraint":

```python
# Posts with no non-spam comment
posts = await Post.doesnt_have(
    "comments", lambda q: q.where(Comment.spam == False)
).get()
```

`or_where_has`, `or_doesnt_have`, and `or_where_relation` OR their condition onto the WHERE:

```python
posts = await (
    Post.where(Post.title == "special")
    .or_where_has("comments")
    .get()
)
```

### Filter and eager-load with one constraint

`with_where_has` filters by a relation **and** eager-loads that relation with the same constraint, so the parent's collection comes back pre-filtered:

```python
posts = await Post.query().with_where_has(
    "comments", lambda q: q.where(Comment.spam == False)
).get()
# posts only contains parents with a non-spam comment, and post.comments holds just those.
```

### Filtering by a parent instance

`where_belongs_to` is the inverse of `where_has` — constrain children by a known parent:

```python
author = await User.find(1)
posts = await Post.query().where_belongs_to(author).get()        # infers the FK relation
posts = await Post.query().where_belongs_to(author, "author").get()  # explicit relation name
```

## Aggregating over relations

```python
# Post count per user (adds .posts_count attribute)
users = await User.with_count("posts").all()
for user in users:
    print(user.name, user.posts_count)

# Sum / avg / min / max of order totals per user
users = await User.with_sum("orders", "total_cents").all()   # .orders_sum_total_cents
users = await User.with_avg("orders", "total_cents").all()   # .orders_avg_total_cents
users = await User.with_min("orders", "total_cents").all()   # .orders_min_total_cents
users = await User.with_max("orders", "total_cents").all()   # .orders_max_total_cents

# Boolean "has any" per user
users = await User.with_exists("orders").all()               # .orders_exists
```

Attribute name pattern: `{relation}_{aggregate}_{column}` — `posts_count`, `orders_sum_total_cents`, `orders_max_total_cents`. `with_count` uses `{relation}_count` and `with_exists` uses `{relation}_exists`.

All of `with_count`/`with_sum`/`with_avg`/`with_min`/`with_max`/`with_exists` accept the method-style FK relations **and** every pivot descriptor (`BelongsToMany`, `MorphToMany`, `MorphedByMany`) — pivot aggregates join through the pivot table — and raise `UnknownRelationError` for an unknown relation.

### Aliasing and constrained aggregates

Rename the result column with `" as <alias>"` (or the `alias=` kwarg), and filter the aggregated rows with a `constraint=` closure:

```python
# Alias the column
users = await User.with_count("orders as order_total").all()  # .order_total

# Count only paid orders
users = await User.with_count(
    "orders", constraint=lambda q: q.where(Order.status == "paid")
).all()

# Sum of paid order totals, under a custom name
users = await User.with_sum(
    "orders", "total_cents", alias="paid_cents",
    constraint=lambda q: q.where(Order.status == "paid"),
).all()
```

Soft-deleted related rows are never aggregated.

### Loading aggregates after the fact

When you already have an instance, compute an aggregate and cache it on the object:

```python
user = await User.find(1)
await user.load_count("orders")               # user.orders_count
await user.load_sum("orders", "total_cents")  # user.orders_sum_total_cents
await user.load_exists("orders")              # user.orders_exists
await user.load_aggregate("orders", "avg", "total_cents")  # avg/min/max
```

Each loader accepts the same `constraint=` closure as its eager counterpart.

### Soft-deletes and relation counts

`has`, `where_has`, `doesnt_have`, and `with_count` honour the related model's soft-delete scope — trashed related rows are never counted or matched. A blog whose only comment has been soft-deleted has zero comments for `has("comments")` and `with_count("comments")`, just like Eloquent.

## N+1 prevention

Method-style FK relations can't silently N+1: reading one is always an explicit call (`user.posts().get()`), never an attribute access that fires a hidden query. Eager-load with `with_()` and the call serves from the per-instance cache instead of querying:

```python
# one query for users + one for posts
users = await User.with_("posts").all()
for user in users:
    posts = await user.posts().get()    # cache hit, no query

# Without with_(), each call runs its own scoped query — but it's explicit, not hidden
user = await User.find(1)
posts = await user.posts().get()        # one query, by your own hand
```

The pivot and polymorphic descriptors (`BelongsToMany`, `MorphOne`, `MorphMany`, `MorphToMany`) enforce `lazy="raise_on_sql"`, so accessing one without eager loading raises `sqlalchemy.exc.InvalidRequestError` at the offending line rather than issuing a silent query.

### Testing for N+1

Use `QueryLog.assert_max_queries` to verify a code path issues at most N queries:

```python
from arvel.database.query_logging import QueryLog


async def test_list_users_no_n_plus_one() -> None:
    await User.factory().create_many(10)

    with QueryLog.assert_max_queries(2):
        users = await User.with_("posts").all()
        for user in users:
            _ = await user.posts().get()    # cache hit, must not query
```

The context manager raises `AssertionError` if the actual query count exceeds the limit.

## Where to next?

- [Arvent: Getting Started](arvent.md) — defining models and basic queries.
- [Collections](arvent-collections.md) — what relations return.
- [Migrations](migrations.md) — schema setup including `t.morphs(...)`.
- [Database Testing](database-testing.md) — keeping tests clean and fast.
