# Queries

Reading and writing rows, plus reusable query scopes. See also
[Relationships](relationships.md) for relation queries.

## Querying

```python
posts = await Post.where(published=True).order_by("-created_at").limit(10).get()
one   = await Post.find(1)
first = await Post.where("views", ">", 100).first()
count = await Post.where(published=True).count()
page  = await Post.paginate(per_page=20)   # a LengthAwarePaginator — see Pagination
```

`paginate()` returns a [paginator](../pagination.md) (iterable over the page of rows, with
`total()`/`current_page()`/`last_page()` accessors, Laravel JSON shape, and `links()` HTML),
not a plain dict.

The builder carries the everyday Laravel query methods:

```python
await Post.where_in("status", ["draft", "review"]).get()
await Post.where_not_in("status", ["archived"]).get()
await Post.where_between("views", [100, 1000]).get()        # also where_not_between
await Post.when(tag, lambda q, value: q.where(tag=value)).get()  # conditional clause; the truthy
                                                                # value is passed (Laravel style)
await Post.when(tag, lambda q: q.where(tag=tag)).get()      # 1-arg form (close over it) also works
await Post.unless(archived, lambda q: q.where("status", "!=", "archived")).get()  # inverse of when
await Post.order_by("views", "desc").skip(10).take(5).get() # skip/take alias offset/limit
await Post.where(published=True).pluck("title")             # ["Hello", …] (or pluck("title","id") → dict)
await Post.where(slug=s).value("title")                     # one column of the first row
await Post.find_or_fail(1)                                  # ModelNotFound on miss → HTTP 404
await Post.where(slug=s).first_or_fail()                    # same — no manual `if None: abort(404)`
```


## Inserts, updates, deletes

```python
post = await Post.create(title="Hello", body="…")     # mass-assignment guarded by __fillable__
post.title = "Edited"
await post.save()                                      # only when dirty
await post.delete()

await Post.where(draft=True).update({"published": True})
user = await User.first_or_create({"email": e}, {"name": n})
```


## Scopes

Reusable query constraints. A **local** scope is a `scope_*` method callable as a query method;
a **global** scope applies to every query for the model:

```python
class Post(Model):
    def scope_published(self, query):         query.where(published=True)
    def scope_authored_by(self, query, user): query.where(user_id=user.id)

await Post.published().authored_by(ada).get()

Post.add_global_scope("not_archived", lambda q: q.where_null("archived_at"))
await Post.get()                              # archived rows excluded automatically
await Post.without_global_scope("not_archived").get()
```

Prefer to name the method after the scope itself? Decorate it with `@scope` instead of using the
`scope_` prefix — the method name *is* the query method:

```python
from arvel import scope

class Post(Model):
    @scope
    def published(self, query):         query.where(published=True)
    @scope
    def authored_by(self, query, user): query.where(user_id=user.id)

await Post.published().authored_by(ada).get()   # identical call site
```

Both styles are equivalent and may be mixed on the same model; `@scope` just frees the name from
the prefix.
