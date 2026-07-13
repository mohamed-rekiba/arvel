# ORM: Collections

Every ORM query that returns multiple models — `Model.all()`, `.where(...).get()`, a to-many relation —
hands you a `ModelCollection`, not a plain list. It is a superset of the general
[Collection](../collections.md): the full fluent surface (`map`/`filter`/`pluck`/`where`/…) comes
along, plus model-aware batch operations.

## Introduction

Because `ModelCollection` also implements `Sequence`, it behaves like a list where you expect one —
iterate it, index it, `len()` it — so existing list-style code keeps working:

```python
users = await User.where(active=True).get()   # a ModelCollection[User]

for user in users:
    print(user.name)

first = users[0]
count = len(users)

names = users.pluck("name").all()             # inherited Collection methods
adults = users.filter(lambda u: u.age >= 18)
```

> A **raw** table-builder query (no model bound, no hydration) still returns a plain `list[dict]`;
> only *hydrated* model results become a `ModelCollection`.

## Model-aware methods

On top of the fluent `Collection` API, `ModelCollection` adds operations that only make sense for a
set of models:

### Keys & lookup

```python
users.model_keys()          # [1, 2, 3] — the primary keys
users.find(2)               # the member with pk 2, or None
users.contains(some_user)   # membership by primary key
```

### Eager loading

Load relations for the whole set with **one batched query per relation** (a single `WHERE IN`
across all members) — no N+1:

```python
posts = await Post.all()
await posts.load("author", "comments")       # one batched query for author, one for comments
await posts.load_missing("author")           # skip any already loaded
```

### Refetching

```python
fresh = await users.fresh()      # one batched re-query of these rows
```

### Filtering by key & serialization

```python
users.only([1, 2])               # keep members with these primary keys
users.except_([3])               # drop members with these primary keys
users.make_hidden("email")       # hide attributes across every member
users.make_visible("ssn")        # reveal normally-hidden attributes
users.to_dict()                  # [ {...}, {...} ] — each model serialized
users.to_json()
```

### Back to a query

```python
users.to_query()                 # a fresh WHERE pk IN (...) Builder over these members
```

## See also

- [Collections](../collections.md) — the fluent base API inherited here.
- [Relationships](relationships.md) — what `load()` / `load_missing()` eager-load.
- [API Resources](resources.md) — shaping a collection into a JSON response.
