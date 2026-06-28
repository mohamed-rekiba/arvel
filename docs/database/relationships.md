# Relationships

```python
class User(Model):
    def posts(self):   return self.has_many(Post)
    def profile(self): return self.has_one(Profile)

class Post(Model):
    def author(self):  return self.belongs_to(User)

await user.posts().get()                               # lazy
users = await User.with_("posts").get()                # eager — one batched WHERE IN, no N+1
```

**A relation *is* a query builder** (Laravel) — constrain it, count it, and create/save through it:

```python
await user.posts().where(published=True).order_by("-created_at").get()
await user.posts().count()
post = await user.posts().create(title="Hi")           # foreign key set to the parent automatically
await user.posts().save(existing_post)                  # sets the FK + persists

# belongs_to: associate / dissociate set or clear the child's foreign key
post.author().associate(user)                          # post.user_id = user.id (save the post to persist)
post.author().dissociate()                             # post.user_id = None
owner = await post.author().where(active=True).first()
```

**Many-to-many** (`belongs_to_many`) manages the pivot table and can carry + query pivot columns:

```python
class User(Model):
    def roles(self): return self.belongs_to_many(Role)

await user.roles().attach(role_id, assigned_by="admin")  # extra pivot columns supported
await user.roles().detach(role_id)                       # detach() with no arg clears all
await user.roles().sync([1, 2, 3])                       # exact set
await user.roles().sync_without_detaching([4])           # add missing, keep the rest
await user.roles().toggle([1, 2])                        # attach absent / detach present
await user.roles().update_existing_pivot(role_id, assigned_by="system")
await user.roles().with_pivot("assigned_by").get()       # expose pivot data on each result
await user.roles().where_pivot("assigned_by", "admin").count()
await user.roles().where("active", "=", True).get()      # constrain the related model
```

The full relation set: `has_one`/`has_many`/`belongs_to`/`belongs_to_many`,
`has_one_through`/`has_many_through`, and the polymorphic family
`morph_one`/`morph_many`/`morph_to`/`morph_to_many`/`morphed_by_many`.

**Through relations** reach a far model via an intermediate — `has_one_through` returns a
single row (or `None`), `has_many_through` a list:

```python
class Country(Model):
    def first_post(self): return self.has_one_through(Post, User)   # Country → User → Post
    def posts(self):      return self.has_many_through(Post, User)
```

**Polymorphic (morph)** relations let many models share one related table by storing a
`{name}_id` + `{name}_type` pair — e.g. comments that belong to either a post or a video:

```python
class Comment(Model):
    def commentable(self): return self.morph_to("commentable")     # resolves Post or Video

class Post(Model):
    def comments(self): return self.morph_many(Comment, "commentable")

await post.comments().get()
parent = await comment.commentable().get()             # the owning Post/Video
```

In a migration, declare the pair with `t.morphs("commentable")` (or `t.nullable_morphs(...)`)
— it creates `commentable_id` + `commentable_type` with the names the relations read.


## Relationship queries & aggregates

Filter by, and count, related rows without N+1:

```python
await User.has("posts").get()                                  # users with >=1 post
await User.doesnt_have("posts").get()
await User.where_has("posts", lambda q: q.where(published=True)).get()

# with_where_has applies ONE constraint twice: it filters the users AND eager-loads only
# the matching posts — so each returned user's .posts holds just the published ones.
await User.with_where_has("posts", lambda q: q.where(published=True)).get()

await User.with_count("posts").get()         # each user gets a posts_count
await Shop.with_sum("items", "price").get()  # items_sum
await Shop.with_avg("items", "price").get()  # items_avg
await Shop.with_exists("items").get()        # boolean items_exists
```

For a **grouped** aggregate — totals per group rather than per row — pair `select_raw()` (a raw
SQL select expression `select()` can't name) with `group_by()`:

```python
stmt = (
    Sale.select_raw("region, sum(amount) AS total")
    .group_by("region")
    .order_by("region")
    .to_select()
)
rows = await app("db").fetch_all(stmt)        # [{"region": "eu", "total": 5}, …]
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

