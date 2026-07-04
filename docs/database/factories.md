# Factories

Generate model instances for tests and seeders. Subclass `Factory`, set `model`, and implement
`definition()` (use `self.faker` for fake data):

```python
from arvel.database import Factory

class UserFactory(Factory[User]):
    model = User
    def definition(self):
        return {"name": self.faker.name(), "email": self.faker.unique.email()}

await UserFactory().create()                  # one persisted User
user = UserFactory().make(name="Ada")         # one unsaved instance, with an override
UserFactory().raw()                           # just the attribute dict (no model)
```

`count(n)` returns a batch whose `make`/`create` return lists; `state` layers overrides (a dict or
`callable(attrs) -> dict`); `sequence` cycles values across the batch:

```python
await UserFactory().count(3).create()                          # 3 persisted users
await UserFactory().state({"admin": True}).create()            # composable; immutable (returns a copy)
await UserFactory().count(2).sequence({"name": "Alice"}, {"name": "Bob"}).create()
```

Resolution order is `definition()` → `state` (in order) → `sequence[i]` → explicit overrides.

## `Model.factory()`

A `Factory` subclass registers itself for its `model` as soon as it's defined (import it — a
seeder or test module that never imports `PostFactory` never gets it registered), so
`Model.factory()` resolves it by convention:

```python
class PostFactory(Factory[Post]):
    model = Post
    def definition(self): return {"title": self.faker.sentence()}

await Post.factory().create()                 # same as await PostFactory().create()
await Post.factory().count(3).create()
```

Override the convention lookup with an explicit `__factory__` when you need a non-default factory:

```python
class Post(Model):
    __factory__ = SomeOtherFactory
```

## Relationship factories

`has`/`for_` wire up related rows — both only take effect on `create`/`create_many` (there's no
persisted parent row to point at from `make`). Both derive the foreign-key column from the named
relation method on the model (`belongs_to`/`has_many`/`has_one`'s own convention), or take an
explicit `foreign_key=` override:

```python
# belongs-to: create (or reuse) the parent, then set the child's FK
post = await PostFactory().for_(UserFactory(), "user").create()

# has-many: after creating the parent, create `count` related rows with the FK set
user = await UserFactory().has(PostFactory(), "posts", 3).create()
user = await UserFactory().has(PostFactory().count(3), "posts").create()   # same thing
```

`recycle` reuses given instance(s) for any `for_` needing that model class, instead of creating a
new parent each time — handy when many factories should share one parent:

```python
admin = await UserFactory().create(role="admin")
posts = await PostFactory().recycle(admin).for_(UserFactory(), "user").count(5).create()
# all 5 posts belong to `admin`; UserFactory().create() is never actually called
```

`after_making`/`after_creating` run a callback (sync or async) on each built/persisted instance, in
the order registered:

```python
await (
    PostFactory()
    .after_making(lambda p: setattr(p, "slug", slugify(p.title)))
    .after_creating(lambda p: search_index.add(p))
    .create()
)
```
