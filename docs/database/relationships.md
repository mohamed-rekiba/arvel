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

## Defining relationships

### One to one

A one-to-one relation links a model to a single related row. Define `has_one` on the parent and
`belongs_to` on the child (which holds the foreign key):

```python
class User(Model):
    def profile(self): return self.has_one(Profile)          # users.id ← profiles.user_id

class Profile(Model):
    def user(self): return self.belongs_to(User)             # profiles.user_id → users.id
```

The foreign key defaults to `<parent>_id` (`user_id`) and the local/owner key to the primary key;
pass `foreign_key=` / `local_key=` (or `owner_key=` on `belongs_to`) to override.

### One to many

A parent with many children — `has_many` on the parent, `belongs_to` on the child:

```python
class Post(Model):
    def comments(self): return self.has_many(Comment)        # posts.id ← comments.post_id

class Comment(Model):
    def post(self): return self.belongs_to(Post)
```

### Many to many

Many-to-many relations use a **pivot** table. `belongs_to_many` on both sides; the pivot name
defaults to the two model names, snake-cased and sorted (`role_user`):

```python
class User(Model):
    def roles(self): return self.belongs_to_many(Role)       # via the role_user pivot

class Role(Model):
    def users(self): return self.belongs_to_many(User)
```

Manage the pivot rows with `attach`/`detach`/`sync`, and carry extra pivot columns with
`with_pivot`:

```python
def roles(self):
    return self.belongs_to_many(Role, pivot="role_user").with_pivot("assigned_at").as_("membership")

await user.roles().attach(role.id, assigned_at="2026-06-01")
(await user.roles().get())[0].membership["assigned_at"]
await user.roles().where_pivot("assigned_at", "2026-06-01").get()
```

### Has many through

Reach a distant relation *through* an intermediate model — a country's posts through its users:

```python
class Country(Model):
    def posts(self): return self.has_many_through(Post, User)   # country → users → posts
```

`has_one_through` is the single-result variant. Both accept `first_key=`/`second_key=` to override
the intermediate and far foreign keys.

### Polymorphic relations

A polymorphic relation lets a child belong to more than one model type on a single association. A
`Comment` (or `Image`) can attach to a `Post` **or** a `Video` via a `{name}_id` / `{name}_type`
column pair (set up with `t.morphs("commentable")` in the migration):

```python
class Comment(Model):
    def commentable(self): return self.morph_to("commentable")   # → the owning Post or Video

class Post(Model):
    def comments(self): return self.morph_many(Comment, "commentable")

class Video(Model):
    def comments(self): return self.morph_many(Comment, "commentable")
```

`morph_one` is the one-result variant. For a **many-to-many** polymorphic relation (tags shared
across posts and videos), use `morph_to_many` on the owner and `morphed_by_many` on the tag:

```python
class Post(Model):
    def tags(self): return self.morph_to_many(Tag, "taggable")

class Tag(Model):
    def posts(self): return self.morphed_by_many(Post, "taggable")
```

## Related collections

`Model.all()`, `Model.query().get()`, and every many-relation `get()` return a **`ModelCollection`** — a model-aware [Collection](collections.md) with batch operations (`load`/`load_missing`, `model_keys`/`find`, `fresh`, `only`/`except_`). See [ORM: Collections](collections.md) for the full API.

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
