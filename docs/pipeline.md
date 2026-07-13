# Pipeline

`Pipeline` sends a value **through** a list of pipes to a final destination — the same onion shape
arvel uses for its HTTP [middleware](middleware.md). The key thing to unlearn coming from a simple `map`/`reduce`
chain: a pipe isn't a plain transform. It receives `(value, next)` and decides **whether and how**
to call `next` — so it can run logic before *and after* the rest of the pipeline, or stop the
chain entirely. That's what makes it an **onion**, not a pipe in the Unix sense.

```python
from arvel.support import Pipeline

async def log_it(value, next):
    print("before:", value)
    result = await next(value)
    print("after:", result)
    return result

async def double(value, next):
    return await next(value * 2)

async def destination(value):
    return value + 1

result = await Pipeline().send(5).through([log_it, double]).then(destination)
# before: 5
# after: 11
# result == 11
```

Order matters the way you'd expect from nested wrapping: the **first** pipe in `through([...])` is
the **outermost** layer. With pipes `[a, b]`, the call order is `a`-before → `b`-before →
destination → `b`-after → `a`-after.

## `then` vs `then_return`

- `then(destination)` calls `destination(value)` with whatever the pipes passed along, and returns
  its result.
- `then_return()` has no destination — it returns the piped value as-is (equivalent to
  `then(lambda v: v)`).

```python
value = await Pipeline().send(5).through([double]).then_return()   # 10
```

## Short-circuiting

A pipe that never calls `next` stops the chain right there — nothing downstream runs:

```python
def gatekeeper(value, next):
    if not value.get("authorized"):
        return "denied"          # `next` is never called
    return next(value)

result = await Pipeline().send({"authorized": False}).through([gatekeeper]).then(handle)
# result == "denied" — `handle` never ran
```

## Object pipes — `via`

A pipe can be an object instead of a function; `Pipeline` calls a named method on it (`handle` by
default):

```python
class EnsureAdmin:
    async def handle(self, request, next):
        if not request.user.is_admin:
            raise PermissionError()
        return await next(request)

await Pipeline().send(request).through([EnsureAdmin()]).then(controller)
```

Use `via("method_name")` to pick a different method — handy for reusing one class across
different pipelines with different entry points:

```python
class Normalize:
    async def process(self, value, next):
        return await next(value.strip().lower())

await Pipeline().send("  HI  ").through([Normalize()]).via("process").then_return()  # "hi"
```

## The 1-arg transform shortcut

Most pipes don't need before/after logic or short-circuiting — they just transform the value and
move on. Writing `(value, next): return next(fn(value))` every time is noise, so a **plain 1-arg
callable** is auto-adapted into that shape:

```python
def upper(value: str) -> str:
    return value.upper()

async def trim(value: str) -> str:
    return value.strip()

result = await Pipeline().send("  hi  ").through([trim, upper]).then_return()  # "HI"
```

Sync and async 1-arg callables both work, and you can freely mix them with full `(value, next)`
pipes in the same `through([...])` list.

## Sync and async pipes mix freely

A pipe function can be `def` or `async def` — both work in the same pipeline. A sync pipe that
wants to continue the chain simply `return`s `next(value)` (the awaitable chain) rather than
`await`-ing it itself; `Pipeline` awaits it on the pipe's behalf:

```python
def sync_pipe(value, next):
    return next(value)          # no `await` needed — Pipeline resolves it

async def async_pipe(value, next):
    return await next(value)    # awaits directly, since it's already a coroutine

await Pipeline().send(1).through([sync_pipe, async_pipe]).then_return()
```

## No container coupling (v1)

Pipes here are **instances or callables you construct yourself** — not class names resolved through a
container the way [middleware](middleware.md) classes are. That keeps the API dependency-free; DI-based
pipe resolution can layer on top later without breaking this contract.

## Common mistakes & gotchas

- **Forgetting to call `next`.** If a pipe is supposed to continue the chain but doesn't, the
  pipeline silently short-circuits — the destination and every downstream pipe never run. That's
  sometimes exactly what you want (the gatekeeper example above); make sure it's intentional.
- **Assuming the last pipe in the list runs last.** It's the opposite — the **first** pipe wraps
  everything else, so it runs first (before) and last (after).

## See also

- [Helpers & Collections](helpers.md) — `pipe()` for a simple, non-onion transform chain.
- [Context](context.md) — often threaded through a pipeline alongside the value.
