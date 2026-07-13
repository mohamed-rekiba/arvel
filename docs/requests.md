# Requests

Every handler receives a `Request` — a typed wrapper over the incoming HTTP request. It exposes the
path and method, headers and cookies, and a rich **input bag** over the merged query string and body.

## The basics

```python
async def show(request):
    request.path()                 # "/posts/7"
    request.method()               # "GET"
    request.header("accept")       # a header value, or None
    request.query("page", 1)       # a query-string value, with a default
    await request.json()           # the parsed JSON body
```

## The input bag

`input()` reads from the merged query string **and** body (body wins on a key collision), with
dot-notation into nested bodies:

```python
await request.input("email")               # from query or body
await request.input("address.city")        # dot-path into a nested body
await request.input()                      # the whole merged dict
await request.only(["email", "name"])      # just these keys
```

### Typed reads

The typed getters coerce (or fall back to a default) so you don't hand-parse:

```python
await request.string("name")               # str
await request.integer("page", 1)           # int
await request.boolean("remember")          # "1"/"true"/"on"/"yes" → True
```

### Presence & auth

```python
request.bearer_token()                     # the Authorization: Bearer token, or None
```

Input arrives **normalized** — strings are trimmed (password
fields are exempt from trimming) and `""` becomes `None`, courtesy of the global middleware. See [Middleware](middleware.md).

## Form requests

For anything beyond an ad-hoc read, describe the shape once with a **form request**: a typed struct
that declares its validation `rules()` and (optionally) an `authorize()` check. The framework
validates the incoming body against it before your handler runs, and hands you the validated data:

```python
from arvel.validation import FormRequest

class StorePost(FormRequest):
    title: str
    body: str

    @classmethod
    def rules(cls):
        return {"title": "required|string|max:200", "body": "required"}

    def authorize(self) -> bool:
        return True                        # or gate on the current user
```

```python
async def store(request, data: StorePost):     # validated + authorized before this runs
    post = await Post.create(title=data.title, body=data.body)
    return post
```

A failed rule returns a `422` with the per-field error map; a failed `authorize()` returns `403`.
For the full rule set, custom rules, and localized messages, see [Validation](validation.md).

## See also

- [Responses](responses.md) — building what you send back.
- [Validation](validation.md) — the rules the form request runs.
- [Middleware](middleware.md) — the input normalization applied before your handler.
