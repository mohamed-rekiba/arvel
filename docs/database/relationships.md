# Relationships

Rows in one table point at rows in another — a user *has many* posts, a post *belongs to* a user,
posts and tags are *many-to-many*. arvel models those links as **methods** on the model. Each method
declares the relation once; calling it gives you a query you can filter, and eager-loading it pulls
the related rows in a single extra query — no hand-written joins, and no N+1.

```python
class User(Model):
    def posts(self): return self.has_many(Post)
    def profile(self): return self.has_one(Profile)

class Post(Model):
    def author(self): return self.belongs_to(User)

await user.posts().get() # lazy
users = await User.with_("posts").get() # eager — one batched WHERE IN, no N+1
post = await Post.with_("author").first() # with_(...).first() eager-loads too
```

## Model Collection

`Model.all()`, `Model.query().get()`, and every many-relation `get()` return an
**`ModelCollection`** (`arvel.database.collection.ModelCollection`) — a model-aware
`Collection`, not a plain `list` (though list-style iteration/indexing/`len()` still work; it
implements `collections.abc.Sequence`):

```python
posts = await Post.all()
posts.model_keys() # [1, 2, 3,...] — every member's primary key
posts.find(7) # the member with pk == 7, or None
posts.contains(7) # True — by pk or by passing the model itself
await posts.load("comments") # batch eager-load onto every member — one WHERE IN, no N+1
await posts.load_missing("comments") # like load(), but skips members that already have it
await posts.fresh() # reload every member in ONE batched query
posts.make_hidden("body") # fans Model.make_hidden to every member
posts.only([1, 2]) # members whose pk is in [1, 2]
posts.except_([1, 2]) # the inverse
posts.to_dict() # [{...}, {...}] — every member's to_dict()
posts.to_query() # a fresh Builder: WHERE pk IN (these members' keys)
```

`ModelCollection` also carries the full `arvel.support.Collection` surface (`map`/`filter`/
`pluck`/`where`/…) — a transform that returns a new collection (`map`, `filter`, …) yields a
plain `Collection`, not another `ModelCollection`, since the callback's output isn't
guaranteed to still be models. A **raw** (non-model) table builder's `get()` — no `Model` bound —
still returns a plain `list[dict]`: a raw builder deliberately doesn't wrap its rows in a
`Collection`, keeping untyped table reads simple.

**Loaded relations serialize.** Like the `toArray()`, an eager-loaded relation is included
(nested) in `to_dict()` / a JSON response — a has-many as a list, a has-one/belongs-to as a single
nested object, an empty relation as `null`. Only *loaded* relations are serialized:

```python
post = await Post.with_("author", "comments").first()
post.to_dict()
# {"id": 1, "title": "Hi", "author": {"id": 7,...}, "comments": [{...}, {...}]}
```

**A relation *is* a query builder** — constrain it, count it, and create/save through it:

```python
await user.posts().where(published=True).order_by("-created_at").get()
await user.posts().count()
post = await user.posts().create(title="Hi") # foreign key set to the parent automatically
await user.posts().save(existing_post) # sets the FK + persists

# belongs_to: associate / dissociate set or clear the child's foreign key
post.author().associate(user) # post.user_id = user.id (save the post to persist)
post.author().dissociate() # post.user_id = None
owner = await post.author().where(active=True).first()
```

**Many-to-many** (`belongs_to_many`) manages the pivot table and can carry + query pivot columns:

```python
class User(Model):
    def roles(self): return self.belongs_to_many(Role)

await user.roles().attach(role_id, assigned_by="admin") # extra pivot columns supported
await user.roles().detach(role_id) # detach() with no arg clears all
await user.roles().sync([1, 2, 3]) # exact set — see below
await user.roles().sync_without_detaching([4]) # add missing, keep the rest
await user.roles().toggle([1, 2]) # attach absent / detach present
await user.roles().update_existing_pivot(role_id, assigned_by="system")
await user.roles().with_pivot("assigned_by").get() # expose pivot data on each result
await user.roles().where_pivot("assigned_by", "admin").count()
await user.roles().where("active", "=", True).get() # constrain the related model
```

A many-to-many relation is a full query builder over the related model, scoped to the parent —
`where_in`, `pluck`, `sum`, `chunk`, and the rest all apply the pivot constraint, so
`user.roles().pluck("name")` returns only *this* user's role names. (The `with_pivot` accessor data
rides the native `get()`/eager-load path; a bare `.where(...).get()` returns the scoped models
without it.)

### `sync` — diff-based, pivot-preserving

`sync`/`sync_without_detaching`/`sync_with_pivot_values` are **diff-based**, not
detach-then-reattach: they compare the given ids against what's currently attached, then only
attach the missing ones, detach the extras (when `detaching=True`), and update pivot columns for
retained ids whose given attrs differ. A retained pivot row is **never** dropped and recreated —
any extra pivot data you didn't ask to change survives untouched:

```python
result = await user.roles().sync([1, 3]) # bare id list — no pivot attrs given
result = await user.roles().sync({1: {"note": "x"}, 3: {}}) # or {id: pivot_attrs}
result.attached # [3] — ids newly attached
result.detached # [2] — ids removed (only when detaching=True, the default)
result.updated # [1] — retained ids whose given pivot attrs differed from what's stored

await user.roles().sync_without_detaching([4]) # sync(..., detaching=False): never detaches
await user.roles().sync_with_pivot_values([1, 2], {"note": "bulk"}) # same pivot values on every id

changes = await user.roles().toggle([1, 2]) # {"attached": [...], "detached": [...]}
```

`sync`/`sync_without_detaching`/`sync_with_pivot_values` return a `SyncResult`
(`arvel.database.relations.SyncResult`) — a frozen `attached`/`detached`/`updated` changes map; `toggle` returns a plain `{"attached": [...], "detached": [...]}`
dict.

The full relation set: `has_one`/`has_many`/`belongs_to`/`belongs_to_many`,
`has_one_through`/`has_many_through`, and the polymorphic family
`morph_one`/`morph_many`/`morph_to`/`morph_to_many`/`morphed_by_many`.

**Through relations** reach a far model via an intermediate — `has_one_through` returns a
single row (or `None`), `has_many_through` a list:

```python
class Country(Model):
    def first_post(self): return self.has_one_through(Post, User) # Country → User → Post
    def posts(self): return self.has_many_through(Post, User)
```

**Polymorphic (morph)** relations let many models share one related table by storing a
`{name}_id` + `{name}_type` pair — e.g. comments that belong to either a post or a video:

```python
class Comment(Model):
    def commentable(self): return self.morph_to("commentable") # resolves Post or Video

class Post(Model):
    def comments(self): return self.morph_many(Comment, "commentable")

await post.comments().get()
parent = await comment.commentable().get() # the owning Post/Video
```

In a migration, declare the pair with `t.morphs("commentable")` (or `t.nullable_morphs(...)`)
— it creates `commentable_id` + `commentable_type` with the names the relations read.

**Polymorphic many-to-many** (`morph_to_many` / `morphed_by_many`) supports the same pivot surface
as `belongs_to_many` — extra pivot columns and scoped constraints:

```python
class User(Model, HasRoles):
    def roles(self): return self.morph_to_many(Role, "model", pivot="model_has_roles")

await user.roles().attach(role.id, team_id=3)          # write an extra pivot column
await user.roles().where_pivot("team_id", 3).get()     # scope the query by it
await user.roles().detach(role.id, team_id=3)          # scoped detach
```

This is exactly how the RBAC `HasRoles` mixin scopes roles per team over `model_has_roles` — the
framework backs its own roles/permissions with these relations rather than hand-rolled pivot SQL.


## Relationship queries & aggregates

Filter by, and count, related rows without N+1:

```python
await User.has("posts").get() # users with >=1 post
await User.doesnt_have("posts").get()
await User.where_has("posts", lambda q: q.where(published=True)).get()

# with_where_has applies ONE constraint twice: it filters the users AND eager-loads only
# the matching posts — so each returned user's.posts holds just the published ones.
await User.with_where_has("posts", lambda q: q.where(published=True)).get()

await User.with_count("posts").get() # each user gets a posts_count
await Shop.with_sum("items", "price").get() # items_sum
await Shop.with_avg("items", "price").get() # items_avg
await Shop.with_exists("items").get() # boolean items_exists
```

For a **grouped** aggregate — totals per group rather than per row — pair `select_raw()` (a raw
SQL select expression `select()` can't name) with `group_by()`:

```python
stmt = (Sale.select_raw("region, sum(amount) AS total")
.group_by("region")
.order_by("region")
.to_select()
)
rows = await app("db").fetch_all(stmt) # [{"region": "eu", "total": 5}, …]
```

Grouped queries return computed rows, not whole models, so read them with `fetch_all` (or feed
the builder straight into a materialized view class — see **Advanced** below). `select_raw` used
alone replaces the default `SELECT *`.

Many-to-many carries pivot data:

```python
class User(Model):
    def roles(self):
        return self.belongs_to_many(Role, pivot="role_user").with_pivot("assigned_at").as_("membership")

await user.roles().attach(role.id, assigned_at="2026-06-01")
(await user.roles().get())[0].membership["assigned_at"]
await user.roles().where_pivot("assigned_at", "2026-06-01").get()
```

## Common mistakes & gotchas

- **N+1 from a lazy relation in a loop.** `for u in users: await u.posts()` runs a query per user.
  Eager-load with `User.with_("posts")` to batch it into one `WHERE IN`.
- **Calling vs. awaiting a relation.** `user.posts()` returns a *query* (chain more onto it, then
  `get()`); an eager-loaded relation is read as an attribute (`user.posts` after `with_("posts")`).
- **Mismatched foreign-key names.** The conventions expect `<related>_id` (and `*_id`/`*_type` for
  morphs via `t.morphs(...)`). Pass an explicit key when your columns don't follow the convention.
- **Grouped aggregates as models.** A `select_raw(...).group_by(...)` returns computed rows, not
  models — read them with `fetch_all`, not `get()`.

## See also

- [Queries](queries.md) — the builder relation queries extend.
- [Migrations & Schema](migrations.md) — the foreign keys (`t.foreign_id`, `t.morphs`) relations rely on.
- [API Resources](resources.md) — serializing a model with its loaded relations.
- [CTEs & Recursive Queries](ctes.md) — self-referential trees (a category and its descendants).
