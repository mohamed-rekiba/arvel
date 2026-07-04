# Error handling

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

### Ignoring exceptions

`dont_report(ExcType, ...)` suppresses both the log line and reportable callbacks for
expected exceptions. Each exception **instance** is reported at most once, so a retry
loop re-raising the same instance won't spam your log.
