# Casts & Serialization

## Casts & change tracking

```python
post.was_changed("title")        # since the last save
post.get_original("title")
fresh = await post.fresh()       # re-fetch from the database
```

Casts include `datetime`, `bool`, `int`, `json`, native `enum`, and (via the container)
`encrypted` and `hashed`.

Serialize with `to_dict()` (honors `__hidden__`/`__visible__`/`__appends__`) or `to_json()`
for a JSON string of the same shape — `Date`, `Decimal`, and `Enum` values are encoded for you:

```python
post.to_dict()                   # {"title": ..., "slug": ...}  — hidden keys dropped
post.to_json()                   # '{"title": ..., "slug": ...}'
```
