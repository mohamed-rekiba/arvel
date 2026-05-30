# Error Handling

When you start a new Arvel project, error handling is already configured. The framework catches uncaught exceptions, logs them, and returns a consistent JSON response — without leaking internal details.

## The default behavior

When an exception bubbles out of a handler:

1. Arvel logs the exception with full traceback (structured, via the configured logger).
2. The framework maps the exception class to an HTTP status code.
3. A JSON response is returned to the client — including a code, message, and request ID, but **never** a stack trace.

When debug mode is on (`APP_DEBUG=true`), the response includes the traceback. **Never enable debug in production.**

## Exception → status code mapping

Arvel ships a default mapping. You can override any of these via a custom handler (see below).

| Exception | Status | Code | Notes |
|---|---|---|---|
| `BadRequestException` | 400 | `BAD_REQUEST` | Generic bad input |
| `UnauthenticatedException` | 401 | `UNAUTHENTICATED` | Missing or invalid credentials |
| `AuthorizationException` | 403 | `FORBIDDEN` | From `Gate`, `Policy`, or `FormRequest.authorize()` |
| `NotFoundException` | 404 | `NOT_FOUND` | Manual raise; also the destination for `ModelNotFoundError` (see below) |
| `MethodNotAllowedException` | 405 | `METHOD_NOT_ALLOWED` | Wrong HTTP verb |
| `ConflictException` | 409 | `CONFLICT` | Duplicate resource |
| `ValidationException` (Pydantic) | 422 | `VALIDATION_FAILED` | Field-level errors in `details` |
| `UnprocessableException` | 422 | `UNPROCESSABLE` | Semantically invalid input (not a field-level validation error) |
| `ThrottleException` | 429 | `TOO_MANY_REQUESTS` | From the `Throttle` middleware; sets `Retry-After` header |
| `CsrfException` | 419 | `CSRF_MISMATCH` | From the `Csrf` middleware |
| `ServerErrorException` | 500 | `INTERNAL_ERROR` | Explicit server error |
| Everything else | 500 | `INTERNAL_ERROR` | Generic "something went wrong" — no details leaked |

## The standard error shape

Every Arvel error response follows this shape:

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Request body failed validation.",
    "request_id": "01HQXKZ8...",
    "details": [
      { "field": "email", "issue": "value is not a valid email address" }
    ]
  }
}
```

- `code` — machine-readable identifier (UPPER_SNAKE_CASE).
- `message` — single-sentence human description.
- `request_id` — correlates with logs; share it with users when asking them to report an error.
- `details` — optional array, per-error structured data.

## Raising errors from your code

Use the exception classes directly:

```python
from arvel.http.exceptions import (
    AuthorizationException,
    NotFoundException,
    UnprocessableException,
    ValidationException,
)


@Route.post("/posts/{post_id}/comments")
async def comment(post_id: int, body: dict) -> dict:
    post = await Post.find(post_id)
    if post is None:
        raise NotFoundException("Post not found.")
    if not post.allow_comments:
        raise AuthorizationException("Comments are disabled for this post.")
    if body.get("content", "").strip() == "":
        raise UnprocessableException("Comment body cannot be empty.")
    ...
```

### The `abort()` shorthand

For quick one-liners, `abort()` maps a status code to the right typed exception:

```python
from arvel.support.http_helpers import abort


abort(404)                          # NotFoundException
abort(403, "Billing access only.")  # AuthorizationException with message
abort(422, "Invalid state.")        # UnprocessableException
abort(429)                          # ThrottleException (with retry_after=60)
```

`abort()` always raises — it never returns. The resulting exception follows the standard error shape, so clients get a machine-readable `code` and a human-readable `message`.

## ORM errors → HTTP envelope

`Model.find_or_fail()` and `QueryBuilder.first_or_fail()` raise `ModelNotFoundError` (from `arvel.database.exceptions`), not `NotFoundException`. The HTTP layer doesn't import `arvel.database` directly — that would break the ADR-016 boundary. Instead, the `HttpServiceProvider` registers an **exception translator** that maps `ModelNotFoundError` onto `NotFoundException` before the handler renders the envelope.

```python
from arvel.database.exceptions import ModelNotFoundError


@Route.get("/posts/{post_id}")
async def show(post_id: int) -> Post:
    return await Post.find_or_fail(post_id)  # 404 envelope when the row is missing
```

The mapping covers both the default JSON shape and the RFC 7807 problem+json shape served by `ProblemDetailsHandler`. The original `ModelNotFoundError` is not exposed to clients — only the standard error code and message.

To add a translator for your own foreign exception type:

```python
from arvel.http.exceptions import HttpExceptionHandler, ConflictException


class MyServiceProvider(ServiceProvider):
    def boot(self) -> None:
        handler = self.app.container.make(HttpExceptionHandler)
        handler.add_translator(
            DuplicateOrderError,
            lambda exc: ConflictException(f"Order already exists: {exc.order_id}"),
        )
```

`add_translator()` must run before the FastAPI app is built (in provider `register()` or early `boot()`), since translators are read at `register(app)` time.

## Custom exception handlers

Override the default mapping by registering a handler in a service provider:

```python
from starlette.requests import Request
from starlette.responses import JSONResponse


class ErrorServiceProvider(ServiceProvider):
    async def boot(self) -> None:
        @self.app.exception_handler(StripeApiError)
        async def handle_stripe(request: Request, exc: StripeApiError) -> JSONResponse:
            return JSONResponse(
                {"error": {"code": "PAYMENT_PROVIDER_DOWN", "message": str(exc)}},
                status_code=502,
            )
```

Custom handlers take precedence over the defaults.

## Logging exceptions

Every uncaught exception gets logged with:

- The exception type and message
- The full traceback
- The request method, URI, and `request_id`
- The authenticated user ID (if any)
- The matched route name

Pipe these into your aggregator (Sentry, Datadog, Honeycomb, etc.) via the standard `logging` handlers. See [Logging](logging.md) for the wiring.

## Don't log expected errors at error level

Pydantic validation failures, missing models, and authorization rejections are not errors — they're expected, user-driven outcomes. Arvel logs them at `INFO` level. Reserve `ERROR` for things that suggest a bug or operational issue.

## Reporting back to users

For browser-facing apps that serve HTML, customize the 404 and 500 pages:

```python
@Route.fallback
async def not_found(request: Request) -> HTMLResponse:
    return HTMLResponse(render_template("errors/404.html"), status_code=404)


class ErrorServiceProvider(ServiceProvider):
    async def boot(self) -> None:
        @self.app.exception_handler(500)
        async def server_error(request: Request, exc: Exception) -> HTMLResponse:
            return HTMLResponse(render_template("errors/500.html"), status_code=500)
```

## Where to next?

- [Logging](logging.md) — how error logs are written and shipped.
- [Validation](validation.md) — the 422 path in detail.
- [Authorization](authorization.md) — the 403 path in detail.
