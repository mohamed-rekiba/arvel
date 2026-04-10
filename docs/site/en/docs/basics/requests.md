# Requests

Arvel re-exports Starlette’s `Request` and FastAPI’s parameter helpers, so everything you know about FastAPI path models, query validation, and multipart uploads applies unchanged. Think of the request object as the single entry point for HTTP metadata: method, URL, headers, body, and uploaded files.

## The `Request` object

Import `Request` from `arvel.http` (it is Starlette’s request). It exposes:

- `request.method`, `request.url`, `request.headers`, `request.query_params`
- `await request.body()`, `await request.json()`, `await request.form()`
- `request.state` for arbitrary per-request attributes (including Arvel’s container at `request.state.container` when middleware has run)

```python
from arvel.http import Request, Router

router = Router()


@router.get("/ping")
async def ping(request: Request) -> dict[str, str]:
    return {
        "path": request.url.path,
        "host": request.url.hostname or "",
    }
```

## Query parameters and validation

Use FastAPI’s `Query` for typed query params with defaults and constraints. Arvel does not wrap this layer—validation errors flow through the same mechanisms as vanilla FastAPI.

```python
from arvel.http import Query, Router

router = Router()


@router.get("/search")
async def search(q: str = Query(min_length=1), page: int = Query(1, ge=1)) -> dict[str, object]:
    return {"q": q, "page": page}
```

## Path parameters

Declare path variables in the route string and mirror them in the function signature. FastAPI coerces types and returns 422 on bad input.

```python
@router.get("/items/{item_id}")
async def item(item_id: uuid.UUID) -> dict[str, str]:
    return {"item_id": str(item_id)}
```

## Form and JSON bodies

Post JSON bodies map to Pydantic models or dict annotations. For HTML forms, use `Form` fields or `await request.form()` for ad hoc access.

```python
from arvel.http import Form, Router

router = Router()


@router.post("/login")
async def login(username: str = Form(), password: str = Form()) -> dict[str, str]:
    return {"username": username}
```

## File uploads

Use FastAPI’s `UploadFile` for streamed uploads with metadata (`filename`, `content_type`). For multiple files, accept a list of `UploadFile`.

```python
from arvel.http import File, Router, UploadFile

router = Router()


@router.post("/avatar")
async def avatar(file: UploadFile = File()) -> dict[str, str | None]:
    return {"filename": file.filename, "content_type": file.content_type}
```

## Headers

Read headers case-insensitively via `request.headers.get("x-request-id")` or declare them as `Header()` dependencies when you want validation and OpenAPI docs.

```python
from fastapi import Header

from arvel.http import Router

router = Router()


@router.get("/trace")
async def trace(x_request_id: str | None = Header(default=None)) -> dict[str, str | None]:
    return {"x_request_id": x_request_id}
```

## Input retrieval patterns

- Prefer Pydantic models for JSON bodies so validation is centralized and typed.
- Use `FormRequest` (see the validation chapter) when you need Laravel-style rules, authorization gates, and post-validation hooks on the same object.
- For raw access, `await request.json()` is fine in small endpoints—just handle JSON decode errors or let FastAPI own the body parsing via dependencies instead of double-reading the stream.

## Cookies and clients

`request.cookies` is a standard mapping. `request.client` may be `None` on some transports; check before formatting host/port strings for logs.
