# Responses

Arvel sits on Starlette and FastAPI, so you can return any Starlette `Response` subclass—JSON, plain text, streaming, files—and OpenAPI will stay accurate when you annotate return types. On top of that, Arvel ships small helpers for the responses you reach for constantly, plus an API resource layer for shaping models into consistent JSON envelopes.

## JSON helpers

`json_response(data, status_code=200, headers=None)` wraps Starlette’s `JSONResponse`. Use it when you already have a plain dict or list and do not need a Pydantic response model.

```python
from arvel.http import json_response


async def stats() -> object:
    return json_response({"users": 42}, status_code=200)
```

For richer typing and automatic OpenAPI schemas, prefer returning a Pydantic model or using FastAPI’s `response_model` on the route—both interoperate cleanly with Arvel controllers.

## Redirects and empty bodies

- `redirect(url, status_code=307)` returns a `RedirectResponse` (temporary redirect by default; set `302` or `301` when appropriate).
- `no_content()` returns HTTP 204 with an empty body—ideal for deletes or idempotent updates that do not need a payload.

```python
from arvel.http import no_content, redirect


async def logout() -> object:
    return redirect("/login", status_code=303)


async def remove() -> object:
    await delete_row()
    return no_content()
```

## `JsonResource`

`JsonResource[T]` wraps a single model (or DTO) and converts it through `to_dict()`. Override `to_dict()` to expose only the fields you want; the default uses `model_dump()` when available, otherwise falls back to `vars()`.

`__wrap__` controls the outer key—default `"data"`. Set it to `None` to return the dict without wrapping. Helpers like `when` / `when_loaded` can omit keys by returning `MISSING`, which `to_response()` strips recursively.

```python
from arvel.http import JsonResource

from myapp.models import User


class UserResource(JsonResource[User]):
    __wrap__ = "data"

    def to_dict(self) -> dict[str, object]:
        user = self.resource
        return {"id": user.id, "name": user.name}


async def show() -> dict[str, object]:
    user = await fetch_user()
    return UserResource(user).to_response()
```

## `ResourceCollection`

`ResourceCollection` maps many items through a `JsonResource` subclass. It accepts plain lists, `PaginatedResult`, or `CursorResult`; pagination metadata becomes a `meta` block automatically when applicable. Call `.additional({...})` to merge extra top-level keys (links, quotas, etc.).

```python
from arvel.data.pagination import PaginatedResult
from arvel.http import ResourceCollection


async def index() -> dict[str, object] | list[dict[str, object]]:
    page: PaginatedResult[User] = await users.paginate(page=1, per_page=20)
    return ResourceCollection(UserResource, page).additional({"links": {"self": "/users"}}).to_response()
```

## Streaming and files

For Server-Sent Events, large downloads, or incremental bodies, return Starlette’s `StreamingResponse` or `FileResponse` from your endpoint. Arvel does not hide these types—import them from `starlette.responses` and return them like any other ASGI response.

```python
from starlette.responses import StreamingResponse

from arvel.http import Router

router = Router()


@router.get("/export.csv")
async def export_csv() -> StreamingResponse:
    async def rows():
        yield "id,name\n"
        yield "1,Ada\n"

    return StreamingResponse(rows(), media_type="text/csv")
```

## Error payloads

For operational errors, prefer raising `HttpException` (Arvel’s typed exception) or domain errors mapped by the global exception handlers—responses then use RFC 9457 Problem Details JSON consistently (see the error handling chapter).

## Choosing a pattern

- Quick JSON: `json_response` or plain dict with FastAPI.
- Hypermedia-friendly models: `JsonResource` / `ResourceCollection`.
- Binary or streaming: Starlette response classes directly.
- Strict contracts: Pydantic response models + `response_model` for OpenAPI consumers.
