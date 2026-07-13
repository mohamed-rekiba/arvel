# Error Handling

When you start a new arvel project, error and exception handling is already configured for you. Every
uncaught exception — in HTTP handlers, console commands, queued jobs, or orphan tasks — flows through
one global `ExceptionHandler`. Out of the box it logs the error (`unhandled_exception`) and renders a
safe, content-negotiated response that never leaks internals in production.

## Configuration

The `app.debug` config option (the `APP_DEBUG` env var) determines how much information about an error
is shown to the user. **In production keep it `False`** — a `5xx` shows only generic status text, and
the exception type/detail appear only with debug on.

Customize the handler in one place, `with_exceptions` on the application builder:

```python
# bootstrap/app.py
def _configure_exceptions(handler):
    handler.dont_report(PaymentDeclined)                       # expected — don't log as a bug
    handler.reportable(OrderError, notify_ops)                 # run this on every report
    handler.renderable(TeapotError, lambda e, r: json({"error": "teapot"}, 418))


def create_app() -> Application:
    return (
        Application.configure(str(BASE_PATH))
        .with_exceptions(_configure_exceptions)
        .create()
    )
```

## Handling exceptions

### Reporting exceptions

`reportable(ExcType, callback)` runs your callback whenever a matching exception is reported — send it
to your tracker, page someone, count it. Return `False` to also suppress the default log line:

```python
handler.reportable(OrderError, lambda e: tracker.capture(e))     # log line still written
handler.reportable(NoisyError, lambda e: False)                  # swallow the default log
```

An exception can also own its reporting and rendering: a `report()` method replaces the default log
line (return `False` to keep it too), and a `render(request)` method is consulted before registered
renderables:

```python
class PaymentDeclined(Exception):
    def report(self) -> None:
        metrics.increment("payments.declined")

    def render(self, request) -> dict[str, str]:
        return {"error": "payment_declined"}
```

Give an exception a `context()` method and its keys are merged into the structured log record; a
`handler.context(provider)` registration merges into **every** report (app version, deploy id):

```python
class AuditedError(Exception):
    def context(self) -> dict[str, object]:
        return {"order_id": self.order_id}

handler.context(lambda: {"app_version": "1.4.0"})   # merged into every report
```

### Exception log levels

Pin an exception type to a quieter level — everything else stays `error`:

```python
handler.level(StaleCacheError, "warning")
```

### Ignoring exceptions by type

`dont_report(ExcType, ...)` suppresses both the log line and reportable callbacks for expected
exceptions. Each exception **instance** is reported at most once, so a retry loop re-raising the same
instance won't spam your log. Two more render-preserving forms:

```python
handler.dont_report_when(lambda e: isinstance(e, HttpTimeout) and e.retryable)

class CartExpired(Exception, ShouldntReport): ...   # the marker mixin — never worth a log line
```

### Throttling reported exceptions

High-volume failures (a dead upstream failing thousands of times a minute) can be rate-limited or
sampled. `throttle(fn)` gets each exception and returns a `Limit`, a `Lottery`, or `None`:

```python
from arvel.kernel.exceptions import Limit, Lottery

handler.throttle(lambda e: Limit(max_attempts=10, per_seconds=60)   # 10/min per type
                 if isinstance(e, UpstreamTimeout) else None)
handler.throttle(lambda e: Lottery(1, 100) if isinstance(e, NoisyError) else None)  # 1%
```

### Rendering exceptions

`renderable(ExcType, callback)` registers a custom response for an exception type. The callback
receives `(exc, request)` and returns an `arvel.http.Response` (the `json()` helper builds one) — or
`None` to fall through to the next match or the default render:

```python
from arvel.http.response import json

handler.renderable(TeapotError, lambda e, r: json({"error": "teapot", "msg": str(e)}, 418))
```

Callbacks match by `isinstance`, in registration order; the first non-`None` result wins.

## Custom HTTP error pages

For **HTML** error responses you rarely need a renderable — drop a template in `resources/views/errors/`
named for the status code and arvel renders it automatically when an HTML client hits that error:

```
resources/views/errors/404.html      # rendered for a 404
resources/views/errors/503.html      # rendered for a 503
resources/views/errors/generic.html  # fallback for any status without its own page
```

Each template receives `status`, `message`, and `debug` in scope:

```html
<!-- resources/views/errors/404.html -->
<h1>{{ status }} — Not Found</h1>
<p>{{ message }}</p>
```

Lookup is `errors/<status>.html` → `errors/generic.html` → a minimal built-in page, and applies only
to the HTML render path (JSON/API clients still get the negotiated `{message, errors}` body). It's
fully guarded — a missing or broken template falls back rather than raising.

!!! note "Keep error templates self-contained"
    Error pages render in a **minimal** environment with only `status`, `message`, and `debug` in
    scope — not the usual template globals (`route`, `trans`, `vite`, …) and not `{% extends %}` of a
    layout that uses them. A template that reaches for those raises during render and silently falls
    back to the built-in page. Write error pages as standalone HTML. (For a 5xx, `message` is already
    the generic status text unless `app.debug` is on, so it won't leak internals.)

## HTTP exceptions

Most of the time you don't define an exception class at all — you `abort()` with a status code, and
the handler turns it into a proper HTTP response:

```python
from arvel import abort

async def show(request, post):
    if post.archived:
        abort(404)                       # → 404 "Not Found"
    if not request.user.owns(post):
        abort(403, "That isn't yours.")  # → 403 with your message
    return post
```

`abort(status, message=None)` raises an `HttpException` carrying the status; with no message it uses
the standard status text. It's typed `NoReturn`, so a type-checker narrows the value after an `abort`
guard. Validation failures raise their own `HttpException` (a `422`); see [Validation](validation.md).

### How a response is chosen

The handler renders one exception *content-negotiated* — the same `abort(403)` becomes JSON for an API
client and an HTML error page for a browser, decided by the request's `Accept` header:

- **API-first default → JSON.** With no `Accept` (or `application/json`), you get
  `{"message": "...", "errors": {...}}`. HTML is rendered only when the client asks for `text/html`.
- **`application/vnd.api+json` → JSON:API**, with a `source.pointer` at the offending field.
- **Inertia (`X-Inertia: true`) → the JSON 422 path**, so the front end handles validation inline.
- **A `5xx` never leaks internals in production** — generic status text unless `app.debug` is on.

## A domain exception, end to end

The verbs — `renderable`, `reportable`, `dont_report` — are meant to be used together. A checkout can
fail because a card was declined (expected, not a bug) or an order is in a bad state (worth hearing
about):

```python
class PaymentDeclined(Exception): ...

class OrderError(Exception):
    def __init__(self, order_id: int, reason: str) -> None:
        super().__init__(f"order {order_id}: {reason}")
        self.order_id = order_id

    def context(self) -> dict[str, object]:
        return {"order_id": self.order_id}
```

```python
def _configure_exceptions(handler):
    # a declined card isn't a bug — don't log it, don't page anyone
    handler.dont_report(PaymentDeclined)
    handler.renderable(PaymentDeclined, lambda e, r: json({"error": "payment_declined"}, 402))
    # an order error IS worth knowing about — capture it, render a clean 409
    handler.reportable(OrderError, lambda e: tracker.capture(e))
    handler.renderable(OrderError, lambda e, r: json({"error": "order_failed"}, 409))
```

```python
async def checkout(request, order):
    if not await gateway.charge(order):
        raise PaymentDeclined
    if order.state != "ready":
        raise OrderError(order.id, f"not ready ({order.state})")
    return {"status": "ok"}
```

A declined card returns `402` and your logs stay quiet; a bad order returns `409`, is captured, and
writes one structured line carrying the `order_id` from `context()`. Every entry point routes through
this same handler — you wrote the policy once.

## Common mistakes & gotchas

- **Expecting HTML from an API client.** Rendering is API-first: with no `Accept` header you get JSON.
  Send `Accept: text/html` for the HTML render.
- **Leaking detail from a `5xx`.** In production a `500` shows only generic status text — turn on
  `app.debug` locally to see the exception; don't ship it on.
- **A `renderable` that returns nothing** falls through to the default render — return a `Response`.
- **`reportable` that forgets to return `False`** runs *in addition to* the default log line.

## See also

- [Routing](routing.md) — `abort()` in handlers, and the automatic `404` from route–model binding.
- [Validation](validation.md) — how a failed rule becomes a `422` with per-field `errors`.
- [Logging](logging.md) — the structured log line an unhandled exception writes.
- [Telemetry](telemetry.md) — shipping reported errors to a tracker.
