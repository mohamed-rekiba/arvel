# Attributes, Accessors & Mutators

How a model's attributes are read, written, transformed, serialized, and change-tracked.
Casts (`__casts__`) transform values by *type* — see [Casts](casts.md); this page covers the
per-attribute hooks and the attribute lifecycle around them.

## Accessors

An **accessor** transforms a stored value every time you read the attribute. Define a method
that returns an `Attribute` — the `-> Attribute` return annotation is what marks it (an
unannotated method stays a plain method):

```python
from arvel import Model
from arvel.database import Attribute

class User(Model):
    __fields__ = {"first": str, "last": str}

    def first(self) -> Attribute:
        return Attribute(get=lambda value, attrs: value.title() if value else value)
```

```python
user = await User.create(first="ada", last="lovelace")
user.first          # "Ada" — the accessor ran
user._attributes    # {"first": "ada", ...} — storage is untouched
```

The `get` callable receives `(value, attributes)`: the stored value for this key, and the
model's **raw stored attributes dict**. Raw means post-mutator, pre-accessor/pre-cast — an
accessor reading `attrs["first"]` above sees `"ada"`, not `"Ada"`. Accessors take precedence
over a cast on the same key.

The defining method is stripped from the class at model creation, so `user.first` resolves to
the transformed *value* — you never call it.

### Computed attributes

An accessor doesn't need a column. Combine values on the fly:

```python
class User(Model):
    __fields__ = {"first": str, "last": str}

    def full_name(self) -> Attribute:
        return Attribute(get=lambda value, attrs: f"{attrs['first']} {attrs['last']}".title())
```

`user.full_name` works even though no `full_name` column exists (`value` arrives as `None`).
Computed attributes don't serialize by default — add them to [`__appends__`](#appends) for that.

### Caching expensive accessors

`cached=True` memoizes the computed value per instance — the `get` callable runs once:

```python
def gravatar(self) -> Attribute:
    return Attribute(get=lambda value, attrs: hash_email(attrs["email"]), cached=True)
```

## Mutators

A **mutator** transforms a value on the way *in* — assignment and mass-assignment both route
through it, and what it returns is what gets stored (and persisted):

```python
class User(Model):
    __fields__ = {"first": str}

    def first(self) -> Attribute:
        return Attribute(
            get=lambda value, attrs: value.title() if value else value,
            set=lambda value, attrs: value.strip().lower(),
        )
```

```python
user = await User.create(first="  ADA  ")
user._attributes["first"]   # "ada" — normalized before storage
user.first                  # "Ada" — accessor on the way back out
```

A mutator on a key takes precedence over a cast's write path for that key.

## Appends

`__appends__` folds computed accessors into `to_dict()` / `to_json()` (they have no stored
value, so serialization would otherwise skip them):

```python
class User(Model):
    __appends__ = ["full_name"]
```

```python
user.to_dict()   # {"first": ..., "last": ..., "full_name": "Ada Lovelace"}
```

## Visibility

`__hidden__` drops keys from serialization (secrets, internal columns); `__visible__` is the
allow-list inverse. Per-instance, `make_hidden(*keys)` / `make_visible(*keys)` adjust one
model's serialization without changing the class — `make_visible` reveals a normally-hidden
key (an admin endpoint showing a field the public API hides):

```python
class User(Model):
    __hidden__ = ["password_hash", "email"]

user.to_dict()                          # neither key present
user.make_visible("email").to_dict()    # email included, password_hash still hidden
```

Both also exist on a query result's `ModelCollection`, fanning out to every member:

```python
(await User.all()).make_visible("email")
```

## Dirty tracking

Every model tracks its attributes against the values it was hydrated (or last saved) with:

```python
user.is_dirty()             # any unsaved change?
user.is_clean()             # the inverse
user.last = "Byron"
user.get_dirty()            # {"last": "Byron"} — changed keys with their NEW values
user.get_original("last")   # "Lovelace" — the pre-change value
await user.save()           # persists only the dirty keys; the model is clean again
```

## Primary keys

`__primary_key__` names the key column (default `"id"`, integer, auto-increment). For string
keys generated on insert, mix in one of:

```python
from arvel.database import HasUuids   # UUIDv7 — time-ordered
from arvel.database import HasUlids   # ULID — lexicographically sortable

class Order(HasUuids, Model):
    __fields__ = {"total": int}        # id column handled by the mixin
```

A new `Order` gets its id generated automatically on insert; both formats sort by creation
time, so they index well.
