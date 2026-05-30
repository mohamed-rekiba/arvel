# Requests

Arvel's primary tool for handling HTTP input is the **form request** — a typed Pydantic model with an authorization hook that runs before validation. This is the equivalent of Laravel's `FormRequest` class, expressed in Python's type system.

## Anatomy

```python
from typing import Any
from pydantic import BaseModel, EmailStr

from arvel import FormRequest, Route


class StoreUserPayload(BaseModel):
    name: str
    email: EmailStr


class StoreUser(FormRequest[StoreUserPayload]):
    async def authorize(self, request: Any) -> bool:
        return True


@Route.post("/users")
async def create(form: StoreUser) -> dict[str, str]:
    payload = form.validated()
    return {"created": payload.email}
```

Two behaviors come for free:

1. **Validation** — Arvel hands the request body to Pydantic. Failures become `422 Unprocessable Entity` with structured field errors.
2. **Authorization** — Arvel calls `authorize()` after validation. Returning `False` raises `AuthorizationException`, which becomes `403 Forbidden`.

## Why subclasses, not factories?

Because you keep the type. The handler signature is `(form: StoreUser)`. Both your IDE and the type checker know `form.validated().name` is a `str`. Pydantic models already give you the schema; subclassing lets us bolt on the lifecycle hooks without losing the type.

## Custom authorization

`authorize(request)` is async and receives the live request, so it can inspect headers, cookies, the authenticated user, or your container:

```python
class DeletePostPayload(BaseModel):
    post_id: str


class DeletePost(FormRequest[DeletePostPayload]):
    async def authorize(self, request: Any) -> bool:
        user = request.state.user
        post = await Post.find_or_fail(self.validated().post_id)
        return user.id == post.author_id
```

## Customizing error messages

For per-field messages, attach them to the Pydantic model:

```python
from typing import Annotated
from pydantic import Field


class StoreUserPayload(BaseModel):
    name: Annotated[str, Field(min_length=2, max_length=120)]
    email: EmailStr

    model_config = {"validate_assignment": True}
```

For global messages (e.g. "email already taken"), override `messages()`:

```python
class StoreUser(FormRequest[StoreUserPayload]):
    def messages(self) -> dict[str, str]:
        return {
            "email.unique": "That email is already in use.",
            "name.min_length": "Name must be at least 2 characters.",
        }
```

## Accessing the request directly

If you need the raw request inside your handler (headers, query params, cookies), accept it as a parameter:

```python
from starlette.requests import Request


@Route.post("/users")
async def create(form: StoreUser, request: Request) -> dict[str, str]:
    ip = request.client.host
    user_agent = request.headers.get("user-agent")
    ...
```

FastAPI handles request injection; you don't have to mark anything special.

## Query parameters

Declare query params as typed function arguments:

```python
@Route.get("/search")
async def search(q: str = "", page: int = 1, per_page: int = 20) -> dict:
    ...
```

For complex query objects, use Pydantic with `Query`:

```python
from fastapi import Query


class SearchParams(BaseModel):
    q: str = ""
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)


@Route.get("/search")
async def search(params: SearchParams = Query()) -> dict:
    ...
```

## Cookies and headers

```python
from typing import Annotated
from fastapi import Cookie, Header


@Route.get("/me")
async def me(
    session_id: Annotated[str | None, Cookie()] = None,
    user_agent: Annotated[str | None, Header()] = None,
) -> dict:
    ...
```

## File uploads

```python
from fastapi import UploadFile, File


@Route.post("/avatar")
async def upload(file: Annotated[UploadFile, File()]) -> dict:
    contents = await file.read()
    await Storage.disk("public").put(f"avatars/{file.filename}", contents)
    return {"path": f"avatars/{file.filename}"}
```

`UploadFile` is a Starlette type. It's already typed, async, and streams large files without loading them into memory.

## Content negotiation

`wants_json` tells you whether the caller expects a JSON response. This is useful in middleware or error handlers that need to return either JSON or HTML depending on the client:

```python
from arvel.http import wants_json


async def error_handler(request: Request, exc: Exception) -> Response:
    if wants_json(request):
        return JSONResponse({"error": str(exc)}, status_code=500)
    return HTMLResponse("<h1>Something went wrong</h1>", status_code=500)
```

It checks three signals in order:

1. Path starts with `/api` — always JSON.
2. `Accept` header contains `application/json`.
3. `X-Requested-With: XMLHttpRequest` (legacy XHR sentinel).

## OpenAPI schemas

Form requests automatically appear in your OpenAPI schema. The wrapped Pydantic model is documented as the request body; the route's response model documents the response. Visit `/docs` (Swagger) or `/redoc` to browse the generated spec.

To customize the OpenAPI metadata for a request:

```python
class StoreUser(FormRequest[StoreUserPayload]):
    openapi_summary = "Create a user account"
    openapi_description = "Creates a user with the given name and email."
```

## Where to next?

- [Validation](validation.md) — Pydantic patterns Arvel relies on.
- [Authorization](authorization.md) — Gate and Policy classes for deeper authz.
- [Responses](responses.md) — shaping the data you return.
