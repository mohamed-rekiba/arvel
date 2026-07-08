# Error Handling

Every uncaught exception — in HTTP handlers, console commands, queued jobs, or orphan
tasks — flows through one global `ExceptionHandler`. Out of the box it logs the error
(`unhandled_exception`) and renders a safe, content-negotiated response that never leaks
internals in production. You customize it in one place: `with_exceptions` on the
application builder.

```python
# bootstrap/app.py
def _configure_exceptions(handler):
    handler.dont_report(PaymentDeclined)                       # expected — don't log as a bug
    handler.reportable(OrderError, notify_ops)                 # run this on every report
    handler.renderable(TeapotError, lambda e, r: json({"error": "teapot"}, 418))


def create_app() -> Application:
    return (
        Application.configure(str(BASE_PATH))
        # ...
        .with_exceptions(_configure_exceptions)
        .create()
    )
```

## Raising an HTTP error

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

`abort(status, message=None)` raises an `HttpException` carrying the status. With no message it uses
the standard status text (`404` → "Not Found"). It's typed `NoReturn`, so a type-checker narrows the
value after an `abort` guard — the code below an `abort(404)` knows `post` is non-`None`. Validation
failures raise their own `HttpException` (a `422` carrying the field errors); see
[Validation](validation.md).

### How a response is chosen

The handler renders one exception *content-negotiated* — the same `abort(403)` becomes JSON for an API
client and an HTML error page for a browser, decided by the request's `Accept` header:

- **API-first default → JSON.** With no `Accept` (or an explicit `application/json`), you get
  `{"message": "...", "errors": {...}}`. arvel only renders HTML when the client explicitly asks for
  `text/html`.
- **`application/vnd.api+json` → JSON:API.** Errors come back in the JSON:API shape, and validation
  errors include a `source.pointer` at the offending field so client tooling can map them back.
- **Inertia (`X-Inertia: true`) → the JSON 422 path**, so the front end handles validation inline.
- **A `5xx` never leaks internals in production.** The message is the generic status text unless
  `app.debug` is on — only then do you see the exception type and detail.

## Rendering exceptions

`renderable(ExcType, callback)` registers a custom response for an exception type. The
callback receives `(exc, request)` and returns an `arvel.http.Response` (the `json()`
helper builds one) — or `None` to fall through to the next match or the default render:

```python
from arvel.http.response import json


class TeapotError(Exception):
    pass


handler.renderable(TeapotError, lambda e, r: json({"error": "teapot", "msg": str(e)}, 418))
```

Raise `TeapotError` in any route and the client gets `418 {"error": "teapot", ...}`.
Callbacks match by `isinstance`, in registration order; the first non-`None` result wins.
Unregistered exceptions keep the default behavior: a generic `500` in production, detail
only with `app.debug` on.

## Reporting exceptions

`reportable(ExcType, callback)` runs your callback whenever a matching exception is
reported — send it to your tracker, page someone, count it. Return `False` to also
suppress the default log line:

```python
handler.reportable(OrderError, lambda e: tracker.capture(e))     # log line still written
handler.reportable(NoisyError, lambda e: False)                  # swallow the default log
```

An exception can also own its reporting and rendering: a `report()` method replaces the
default log line (return `False` from it to keep the default too), and a `render(request)`
method is consulted before registered renderables (return `None` to fall through):

```python
class PaymentDeclined(Exception):
    def report(self) -> None:
        metrics.increment("payments.declined")

    def render(self, request) -> dict[str, str]:
        return {"error": "payment_declined"}
```

### Log levels

Pin an exception type to a quieter level — everything else stays `error`:

```python
handler.level(StaleCacheError, "warning")
```

### Throttling

High-volume failures (a dead upstream failing thousands of times a minute) can be
rate-limited or sampled. `throttle(fn)` gets each exception and returns a `Limit`, a
`Lottery`, or `None` for unthrottled:

```python
from arvel.kernel.exceptions import Limit, Lottery

handler.throttle(lambda e: Limit(max_attempts=10, per_seconds=60)   # 10/min per type
                 if isinstance(e, UpstreamTimeout) else None)
handler.throttle(lambda e: Lottery(1, 100) if isinstance(e, NoisyError) else None)  # 1%
```

### Exception context

Give an exception a `context()` method and its keys are merged into the structured log
record:

```python
class AuditedError(Exception):
    def __init__(self, order_id: int) -> None:
        super().__init__(f"order {order_id} failed")
        self.order_id = order_id

    def context(self) -> dict[str, object]:
        return {"order_id": self.order_id}
```

```text
... [error] unhandled_exception error="AuditedError('order 42 failed')" kind=AuditedError order_id=42
```

A `context(provider)` registration on the handler merges `provider()` into **every**
report — app version, deployment id, tenant. Per-exception context wins on key clashes:

```python
handler.context(lambda: {"app_version": "1.4.0"})
```

### Ignoring exceptions

`dont_report(ExcType, ...)` suppresses both the log line and reportable callbacks for
expected exceptions. Each exception **instance** is reported at most once, so a retry
loop re-raising the same instance won't spam your log.

Two more suppression forms, both render-preserving: `dont_report_when(predicate)` for
value-dependent cases, and the `ShouldntReport` marker mixin for types that are never
worth a log line:

```python
handler.dont_report_when(lambda e: isinstance(e, HttpTimeout) and e.retryable)

class CartExpired(Exception, ShouldntReport): ...
```

## A domain exception, end to end

The three verbs — `renderable`, `reportable`, `dont_report` — are meant to be used together. Here's a
realistic case that touches all of them: a checkout that can fail because a card was declined (an
*expected* business outcome, not a bug) or because an order is in a bad state (something you *do* want
to hear about).

Start with the exceptions. Give the one you care about a `context()` so its detail lands in the log:

```python
class PaymentDeclined(Exception):
    """The card was declined — expected, the user just needs to try another."""


class OrderError(Exception):
    def __init__(self, order_id: int, reason: str) -> None:
        super().__init__(f"order {order_id}: {reason}")
        self.order_id = order_id

    def context(self) -> dict[str, object]:
        return {"order_id": self.order_id}
```

Then configure the handler once, at bootstrap, to treat each the way it deserves:

```python
from arvel.http.response import json

def _configure_exceptions(handler):
    # a declined card isn't a bug — don't log it, don't page anyone
    handler.dont_report(PaymentDeclined)
    handler.renderable(PaymentDeclined, lambda e, r: json({"error": "payment_declined"}, 402))

    # an order error IS worth knowing about — capture it, and render a clean 409
    handler.reportable(OrderError, lambda e: tracker.capture(e))
    handler.renderable(OrderError, lambda e, r: json({"error": "order_failed"}, 409))
```

Now your checkout handler just raises — no try/except, no manual response building:

```python
async def checkout(request, order):
    if not await gateway.charge(order):
        raise PaymentDeclined
    if order.state != "ready":
        raise OrderError(order.id, f"not ready ({order.state})")
    return {"status": "ok"}
```

A declined card returns `402 {"error": "payment_declined"}` and your logs stay quiet. A bad order
returns `409 {"error": "order_failed"}`, is captured by your tracker, and writes one structured log
line carrying the `order_id` from `context()`:

```text
... [error] unhandled_exception error="OrderError('order 42: not ready (draft)')" kind=OrderError order_id=42
```

Every uncaught exception in the app routes through this same handler, so this configuration governs
checkout, a background job that retries the charge, and a CLI command that reconciles orders — you
wrote the policy once.

## Common mistakes & gotchas

- **Expecting HTML from an API client.** Rendering is API-first: with no `Accept` header you get JSON,
  not an error page. Send `Accept: text/html` (a browser does) for the HTML render.
- **Leaking detail from a `5xx`.** In production a `500` shows only generic status text — that's
  deliberate. Turn on `app.debug` locally to see the exception; don't ship it on.
- **A `renderable` that returns nothing.** Returning `None` falls through to the next match / the
  default render. Return a `Response` (e.g. via `json(...)`) to actually handle the type.
- **`reportable` that forgets to return `False`.** A reportable callback runs *in addition to* the
  default log line; return `False` if you want your handler to replace it, not double it.
- **Aborting for a not-found bind.** Route–model binding already raises a `404` on a miss — you rarely
  need a manual `abort(404)` for that case (see [Routing](routing.md)).

## How it works

One `ExceptionHandler` sits at the top of every entry point — HTTP, console, queue, orphan tasks — so
there's a single place errors are logged and rendered. On the HTTP path, `render_exception` reads the
status off the exception (`HttpException.status`, or a framework exception's `status_code`), negotiates
the media type from `Accept`, and builds the matching response; reporting runs the registered
`reportable` callbacks and (unless suppressed) writes the structured `unhandled_exception` log line,
merging in any `context()` the exception exposes.

## See also

- [Routing](routing.md) — `abort()` in handlers, and the automatic `404` from route–model binding.
- [Validation](validation.md) — how a failed rule becomes a `422` with per-field `errors`.
- [Telemetry](telemetry.md) — shipping reported errors to a tracker (e.g. Sentry).
- [Providers](providers.md) — where `with_exceptions` fits in application bootstrap.
