# OpenAPI & API docs

Every arvel app ships an OpenAPI document and an interactive docs UI for free — generated from your
routes by [Litestar](https://litestar.dev), not hand-written. Type a handler's request body and return
value with [`arvel.Schema`](validation.md) and the request/response schemas appear automatically; the
whole document is configured from one typed file, `config/openapi.py`.

!!! note "Needs the `[http]` extra"
    Serving the schema runs on Litestar — `uv add 'arvel[http]'`.

## Where it lives

A new app is scaffolded with `config/openapi.py` already wired:

```python
from arvel import env

config = {
    "title": env("APP_NAME", "blog"),
    "version": "0.1.0",
    "description": "The blog API.",
    "path": "/schema",   # docs UI here; raw document at /schema/openapi.json
    "ui": "swagger",     # swagger | redoc | scalar | rapidoc | stoplight
}
```

Boot the app (`arvel serve`) and visit **`/schema`** for the UI, or **`/schema/openapi.json`** for the
raw document. This dict is a *typed view* (`arvel.http.OpenApiSettings`) — keys are validated through
msgspec, so a typo or a wrong type is a clear error, not a silent miss.

## Request & response schemas

Schemas come straight from your handler's type hints. Annotate the return value for a **response**
schema; add a `Schema`-typed parameter for a **request body** schema (it's parsed and validated for you,
then passed to the handler):

```python
from arvel import Route, Schema


class CreateUser(Schema):
    name: str
    email: str


class UserOut(Schema):
    id: int
    name: str


async def store(request, data: CreateUser) -> UserOut:   # request + response schemas
    user = await User.create(name=data.name, email=data.email)
    return UserOut(id=user.id, name=user.name)


Route.post("/users", store, name="users.store")
```

The document now references `CreateUser` (request body) and `UserOut` (response) under
`components.schemas`, and a malformed body returns `400` before your handler runs. The operation's
`operationId` is the **route name** (`users.store`) — clean and stable for client generators.

## Configuring the document

Every key below is optional; set what you need in `config/openapi.py`:

| Key | What it sets |
|-----|--------------|
| `title`, `version`, `description`, `summary` | Document identity |
| `terms_of_service` | Link to your ToS |
| `path` | Where the UI + document are served (default `/schema`) |
| `ui` | The renderer: `swagger` (default), `redoc`, `scalar`, `rapidoc`, `stoplight` |
| `use_handler_docstrings` | Use handler docstrings as operation descriptions (default `True`) |
| `contact` | `{"name": ..., "email": ..., "url": ...}` |
| `license` | `{"name": "MIT"}` |
| `servers` | `[{"url": "https://api.example.com", "description": "production"}]` |
| `tags` | `[{"name": "auth", "description": "Authentication"}]` |
| `external_docs` | `{"url": ..., "description": ...}` |
| `security` | Security schemes — see below |

## Authentication

Define a **security scheme** to get the *Authorize* button in the docs UI (so you can paste a token and
call protected endpoints), then mark the routes that require it.

```python
# config/openapi.py
config = {
    # ...
    "security": {"bearer": True},   # HTTP bearer/JWT scheme → the Authorize button
}
```

```python
# routes/api.py
Route.get("/user", me, name="api.user").secure("bearer")   # shows the lock; requires the scheme
```

By default the scheme is only *advertised* — routes opt in with `.secure(...)`, so public endpoints
(login, health) stay open. To require it on **every** route instead, set a default:

```python
"security": {"bearer": {"format": "JWT", "default": True}},
```

You can also customize the scheme, use an API-key scheme, or an **OpenID Connect** scheme (for an
IdP login like Keycloak — `.secure("oidc")` on the route):

```python
"security": {"bearer": {"format": "JWT", "description": "Paste your access token"}},
"security": {"api_key": {"name": "X-API-Key", "in": "header"}},
"security": {"oidc": {"openIdConnectUrl": "https://idp/realms/app/.well-known/openid-configuration"}},
```

!!! tip "Scaffold it"
    `arvel new myapp --auth` wires all of this up: a bearer login flow, `config/openapi.py` with the
    bearer scheme, and `GET /api/user` marked `.secure("bearer")` while `/api/login` stays public.

`.secure()` documents the contract — enforcement still lives in your middleware/handler (e.g. the
bearer `TokenGuard`). See [Authentication](auth/authentication.md).

## See also

- [Routing](routing.md) — defining and naming the routes the schema is generated from.
- [Validation](validation.md) — `Schema` and validating request input.
- [Authentication](auth/authentication.md) — the bearer-token flow behind a secured route.
