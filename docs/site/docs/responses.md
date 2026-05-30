# Responses

Every Arvel route handler returns a value, and that value becomes the HTTP response. Because the framework sits on FastAPI, you get the same response-shaping machinery — typed return values, custom status codes, headers, streaming, and JSON resources.

## Returning data

The simplest case: return a Python object and let FastAPI serialize it.

```python
@Route.get("/users")
async def list_users() -> list[dict[str, str]]:
    return [{"id": "1", "name": "Alice"}]
```

The return type annotation is the OpenAPI response model. The value is JSON-encoded with FastAPI's `jsonable_encoder`, which handles `datetime`, `UUID`, `Decimal`, Pydantic models, dataclasses, and more.

## Pydantic models as responses

Return a Pydantic model — Arvel serializes it according to the model's `model_dump()` semantics:

```python
from pydantic import BaseModel


class UserOut(BaseModel):
    id: int
    name: str
    email: str


@Route.get("/users/{user_id}", response_model=UserOut)
async def show(user_id: int) -> UserOut:
    user = await User.find_or_fail(user_id)
    return UserOut(id=user.id, name=user.name, email=user.email)
```

Using `response_model=...` lets FastAPI strip unknown fields and validate the shape — useful when your underlying object has more data than the public API exposes.

## JSON resources

For complex transformations between domain models and API output, Arvel ships `JsonResource`:

```python
from arvel.http import JsonResource, ResourceResponse
from starlette.requests import Request


class UserResource(JsonResource[User]):
    def to_dict(self, request: Request) -> dict[str, object]:
        user = self.resource
        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "joined": user.created_at.isoformat(),
        }


@Route.get("/users/{user_id}")
async def show(user_id: int, request: Request) -> ResourceResponse:
    user = await User.find_or_fail(user_id)
    return UserResource(user).response(request)
```

For collections:

```python
@Route.get("/users")
async def index(request: Request) -> ResourceResponse:
    users = await User.limit(50).get()
    return UserResource.collection(users).response(request)
```

`.response(request)` returns a `ResourceResponse` (`JSONResponse` subclass) you can return directly from a FastAPI handler — status code and headers are optional kwargs. Prefer it over manual `to_dict()` when you want a typed Starlette response object.

`JsonResource` keeps your API contract decoupled from your ORM schema and gives you a single place to add computed fields, exclude attributes, or change shape per endpoint.

## Custom status codes

```python
from starlette import status


@Route.post("/users", status_code=status.HTTP_201_CREATED)
async def create(form: StoreUser) -> dict:
    ...
```

For a dynamic status code, return a `JSONResponse`:

```python
from starlette.responses import JSONResponse


@Route.post("/users")
async def create(form: StoreUser) -> JSONResponse:
    payload = form.validated()
    user = await User.create(**payload.model_dump())
    return JSONResponse({"id": user.id}, status_code=201)
```

## Custom headers

```python
from starlette.responses import JSONResponse


@Route.get("/cached")
async def cached() -> JSONResponse:
    return JSONResponse(
        {"data": [...]},
        headers={"Cache-Control": "public, max-age=300"},
    )
```

## Redirects

```python
from starlette.responses import RedirectResponse


@Route.get("/old-path")
async def redirect_to_new() -> RedirectResponse:
    return RedirectResponse(url="/new-path", status_code=301)
```

## File downloads

```python
from starlette.responses import FileResponse


@Route.get("/download/{file_id}")
async def download(file_id: str) -> FileResponse:
    path = await Storage.disk("local").path(file_id)
    return FileResponse(path, filename="report.pdf", media_type="application/pdf")
```

For files in object storage (S3, Azure Blob), return a temporary signed URL instead of streaming:

```python
@Route.get("/download/{file_id}")
async def download(file_id: str) -> dict:
    url = await Storage.disk("s3").temporary_url(file_id, expires_in=300)
    return {"url": url}
```

## Streaming responses

```python
from starlette.responses import StreamingResponse


async def csv_rows() -> AsyncIterator[bytes]:
    yield b"id,name\n"
    for user in await User.order_by("id").all():
        yield f"{user.id},{user.name}\n".encode()


@Route.get("/users.csv")
async def export() -> StreamingResponse:
    return StreamingResponse(csv_rows(), media_type="text/csv")
```

## HTML responses

If you serve HTML, return a `HTMLResponse` or render a Jinja2 template:

```python
from starlette.responses import HTMLResponse


@Route.get("/")
async def home() -> HTMLResponse:
    return HTMLResponse("<h1>Hello, world</h1>")
```

For template rendering, see [Views](#) (coming soon).

## Where to next?

- [Requests](requests.md) — typed input.
- [Validation](validation.md) — input validation patterns.
- [Errors](errors.md) — error response shape.
