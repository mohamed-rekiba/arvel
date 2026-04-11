# Helpers

Every framework ships a grab bag of small utilities that save you from reinventing wheels—dot-notation config access, string casing, pluralization for table names. Arvel exposes these under **`arvel.support`**: **`data_get`**, **`pluralize`**, and **`to_snake_case`**, exported for convenience and used throughout the framework itself (for example when generating code or resolving ORM table names).

They are plain functions—no magic globals—so you can import them explicitly and keep tests deterministic.

## `data_get`

Walk nested **`dict`**, **list**, and object structures using a dotted path. Handy for optional config blobs, JSON payloads, and error objects where you do not want a ladder of `.get()` calls.

```python
from arvel.support import data_get

payload = {"user": {"profile": {"tier": "pro"}}}
tier = data_get(payload, "user.profile.tier", "free")  # "pro"

rows = data_get({"items": [{"id": 1}]}, "items.0.id")  # 1
missing = data_get({}, "nope", "default")  # "default"
```

Paths support numeric segments for list indexing. Pass a **default** as the third argument when the path might not exist.

## `to_snake_case`

Convert **`PascalCase`** or **`camelCase`** identifiers to **`snake_case`**—ideal for filenames, column hints, and codegen that must match Python style.

```python
from arvel.support import to_snake_case

to_snake_case("UserProfile")  # "user_profile"
to_snake_case("HTTPResponse")  # "http_response"
```

Use it when you derive resource names from class names and want consistency without hand-maintaining strings.

## `pluralize`

Turn a singular English word into a plural form for table names and routes. The ORM uses **`pluralize(to_snake_case(ModelName))`** when inferring **`__tablename__`**.

```python
from arvel.support import pluralize, to_snake_case


class BlogPost:
    pass


table = pluralize(to_snake_case(BlogPost.__name__))  # e.g. "blog_posts"
```

English pluralization has edge cases; for production table names you can always set **`__tablename__`** explicitly on models when the helper does not match your dictionary.

## Philosophy

Helpers in Arvel are **boring on purpose**: small, testable, and imported explicitly. They give you Laravel-adjacent ergonomics without hiding dependencies inside facades—so your modules stay clear, and your type checker stays happier.
