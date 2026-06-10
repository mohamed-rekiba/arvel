# Error Handling

<a name="introduction"></a>
## Introduction

When you start a new Arvel project, error handling is already configured for you. Arvel turns exceptions raised during request handling into consistent JSON error responses. You raise a semantic exception — "not found", "forbidden", "validation failed" — and the framework's handler serializes it with the right status code and a uniform body. You never assemble error responses by hand.

<a name="quick-start"></a>
### Quick start

```python
from arvel import NotFoundException
from app.models.post import Post

async def show(post_id: int):
    post = await Post.find(post_id)
    if post is None:
        raise NotFoundException("Post not found.")
    return post.to_dict()
```

Every error serializes to the same envelope — clients parse one shape:

```json
{"error": {"code": "NOT_FOUND", "message": "Post not found.", "details": []}}
```

See [Available exceptions](#available-exceptions) for the full status/code table.

<a name="the-error-envelope"></a>
## The Error Envelope

Every HTTP exception serializes to the same envelope:

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Post not found.",
    "details": [
      {"field": "email", "issue": "The email has already been taken."}
    ]
  }
}
```

- `code` is a stable, machine-readable identifier (`UPPER_SNAKE_CASE`).
- `message` is a human-readable, single-sentence description.
- `details` is optional — present only when the exception carries field-level issues, as validation errors do.

This shape is identical whether the error came from your code, a [form request](validation.md), or FastAPI's own body parsing, so clients only ever parse one format.

<a name="http-exceptions"></a>
## HTTP Exceptions

<a name="available-exceptions"></a>
### Available Exceptions

Arvel provides a typed exception for each common HTTP status. Each carries a fixed status code and machine code:

| Exception | Status | `code` |
|---|---|---|
| `BadRequestException` | 400 | `BAD_REQUEST` |
| `UnauthenticatedException` | 401 | `UNAUTHENTICATED` |
| `AuthorizationException` | 403 | `FORBIDDEN` |
| `NotFoundException` | 404 | `NOT_FOUND` |
| `MethodNotAllowedException` | 405 | `METHOD_NOT_ALLOWED` |
| `ConflictException` | 409 | `CONFLICT` |
| `ValidationException` | 422 | `VALIDATION_FAILED` |
| `UnprocessableException` | 422 | `UNPROCESSABLE` |
| `ThrottleException` | 429 | `TOO_MANY_REQUESTS` |
| `ServerErrorException` | 500 | `INTERNAL_ERROR` |
| `HttpException` | 500 (overridable) | `INTERNAL_ERROR` |

> [!NOTE]
> All of these are importable from the top-level `arvel` package **except** `UnprocessableException`, which lives in `arvel.http.exceptions`. The `CsrfMismatchException` raised by [`VerifyCsrf`](middleware.md#verifycsrf) (419, `CSRF_MISMATCH`) lives in `arvel.http.middleware`.

<a name="throwing-exceptions"></a>
### Throwing Exceptions

Raise an exception anywhere during request handling, and the handler converts it to the matching response:

```python
from arvel import NotFoundException, ValidationException
from arvel.http.exceptions import UnprocessableException

raise NotFoundException("Post not found.")

raise ValidationException(
    "Validation failed.",
    details=[{"field": "email", "issue": "must be unique"}],
)
```

`ThrottleException` requires a `retry_after_seconds`, which the handler emits as a `Retry-After` header:

```python
raise ThrottleException("Slow down.", retry_after_seconds=30)
```

<a name="where-exceptions-come-from"></a>
### Where Exceptions Come From

You'll often encounter these exceptions without raising them yourself:

- `find_or_fail(...)` and missing [route model bindings](routing.md#route-model-binding) surface as `404`s.
- [Form request](validation.md) rule failures raise `ValidationException` (`422`).
- A failed `authorize()` or a denied [gate](../features/authorization.md) check raises `AuthorizationException` (`403`).
- The [`Authenticate`](middleware.md#authenticate) middleware with no user raises `UnauthenticatedException` (`401`).

<a name="custom-http-exceptions"></a>
## Custom HTTP Exceptions

For your own domain errors, subclass `HttpException` and set the status and code:

```python
from arvel import HttpException


class PaymentRequiredException(HttpException):
    status_code = 402
    code = "PAYMENT_REQUIRED"
```

Then raise it like any other:

```python
raise PaymentRequiredException("Your subscription has lapsed.")
```

> [!WARNING]
> Never put internal detail — SQL, stack traces, file paths, secrets — into the `message` of a client-facing exception. Keep messages user-appropriate and [log](../features/logging.md) the internals.

<a name="the-exception-handler"></a>
## The Exception Handler

The exception handler is registered automatically when the application boots (`into_asgi()`). It:

- Serializes `HttpException` subclasses to the [envelope](#the-error-envelope) with their status code.
- Normalizes FastAPI's `RequestValidationError` (body-parsing failures) into the same `422` shape.
- Catches any other unhandled `Exception` and returns a generic `500` with the body `"Something went wrong"` — **no** stack traces, SQL, or internal paths leak to the client, in any environment.

<a name="reporting-and-logging"></a>
### Reporting and Logging

The handler logs as it works: handled `HttpException`s are logged at warning level (with auth and cookie headers redacted), and unhandled exceptions are logged at error level with the exception attached, before the generic `500` is returned. See [Logging](../features/logging.md).

<a name="custom-translators"></a>
### Custom Translators

To map a third-party or library exception to an HTTP response, register a *translator* — a callable that converts the exception into an `HttpException`. Resolve `HttpExceptionHandler` from the [container](../core-concepts/service-container.md) in a provider's `boot()` and add the translator:

```python
async def boot(self) -> None:
    handler = self.app.make(HttpExceptionHandler)
    handler.add_translator(SomeLibraryError, lambda exc: NotFoundException(str(exc)))
```

Arvel registers a few translators by default — for instance, the ORM's `ModelNotFoundError` is translated to `NotFoundException`, and the auth package's exceptions are mapped to their HTTP equivalents.

<a name="problem-details"></a>
### Problem Details (RFC 7807)

Arvel also ships a `ProblemDetailsHandler` (in `arvel.http.problem_details`) that renders errors as `application/problem+json` per RFC 7807. It's opt-in: bind it in place of the default `HttpExceptionHandler` in the container.

It handles the same surface as the default handler — `HttpException` subclasses, FastAPI validation errors, and your registered translators — and installs the same catch-all for unhandled `Exception`s, rendering a generic `500` problem document (`"Something went wrong"`, no traceback) instead of letting it escape as a raw `500`.
