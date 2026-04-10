# Error Handling

Arvel standardizes HTTP errors around **RFC 9457 Problem Details** JSON: `type`, `title`, `status`, optional `detail`, and `instance`. That gives browsers, mobile clients, and proxies a predictable shape without sacrificing structured logging on the server. You still raise normal Python exceptions in your domain layer—the framework translates them at the edge.

## `install_exception_handlers`

Call `install_exception_handlers(app, debug=False)` once when building your FastAPI application. It registers handlers for:

- Starlette/FastAPI `HTTPException` (the generic one from Starlette)
- Arvel’s own `HttpException`
- `RequestValidationError` (FastAPI/Pydantic validation)
- SQLAlchemy `DBAPIError` (database driver failures)
- A final catch-all for `Exception` with full logging

Problem responses use `application/problem+json` and include the request path in `instance`.

```python
from fastapi import FastAPI

from arvel.http import install_exception_handlers

app = FastAPI()
install_exception_handlers(app, debug=app.debug)
```

## Arvel `HttpException`

Use `HttpException` when you want an HTTP status and message without reaching for Starlette’s class directly. It carries `status_code` and `detail`, maps cleanly through Arvel’s handler, and participates in the same Problem Details format.

```python
from arvel.http import HttpException


async def must_be_admin(is_admin: bool) -> None:
    if not is_admin:
        raise HttpException(403, "Insufficient permissions")
```

Specialized subclasses like `ModelNotFoundError` and `InvalidSignatureError` encode common cases with stable messages for APIs and signed URLs.

## Domain exception registration

`register_domain_exception(ExceptionType, status_code)` maps your domain errors to HTTP statuses before they bubble to the generic handler. The framework logs context (including `ArvelError` attributes when present) and returns Problem Details with `detail=str(exc)`.

Built-in mappings include examples like `NotFoundError -> 404` and `AuthenticationError -> 401`; extend the map for your own hierarchy.

```python
from arvel.http.exception_handler import register_domain_exception

from myapp.errors import SeatUnavailableError

register_domain_exception(SeatUnavailableError, 409)
```

After you register domain types with `register_domain_exception`, call `register_exception(app)` once so those mappings become active exception handlers on the FastAPI instance. Order matters: register your custom types **before** `register_exception` iterates the map.

## Validation errors

When FastAPI rejects a body or query, the handler flattens errors into a readable `detail` string. With `debug=True`, the Problem payload can include an `errors` array mirroring FastAPI’s structure—turn this on locally, keep it off in production to avoid leaking input shapes.

## Database and unexpected errors

Database exceptions log structured fields (request method, URL, request id when available) and return a safe 500 Problem response. Unhandled exceptions log the traceback server-side; only when `debug=True` does the client see exception names and messages—mirroring Laravel’s `APP_DEBUG` story.

## Debugging tips

- Correlate logs with `x-request-id` when the context middleware populates it; the handler forwards that header on error responses when known.
- Prefer raising typed domain errors + `register_domain_exception` over raw strings in controllers—tests can assert on exception types, and handlers stay thin.
- For form validation you own end-to-end, catch `ValidationError` from Arvel’s validator and return your own JSON alongside or instead of FastAPI’s default—just stay consistent with your API’s error contract.
