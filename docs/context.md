# Context

`Context` is an ambient, request/job-scoped key/value store — a place
to stash things like a request ID, tenant, or trace span that many layers of code want to read
without threading them through every function signature. It's backed by Python's `contextvars`,
so it's **safe across concurrent `asyncio` tasks**: two requests running at the same time (or two
tasks in an `asyncio.gather`) never see each other's context, even though `Context` itself looks
like a single global namespace.

```python
from arvel.support import Context

Context.add("request_id", "abc123")
Context.get("request_id")            # "abc123"
Context.all()                        # {"request_id": "abc123"}
Context.has("request_id")            # True
Context.forget("request_id")
```

`Context` is a **static namespace** — like `Str`/`Number`, you never instantiate it.

## Stacks

`push`/`pop` treat a key's value as a stack, useful for things like a breadcrumb trail:

```python
Context.push("trace", "controller")
Context.push("trace", "service", "repository")
Context.stack_contains("trace", "service")   # True
Context.pop("trace")                          # "repository"
Context.pop("trace")                          # "service"
```

## Counters

```python
Context.increment("queries")        # 1
Context.increment("queries")        # 2
Context.increment("queries", 5)     # 7
Context.decrement("queries")        # 6
```

## Hidden context

Hidden values are stored separately and **never appear in `all()`** — for things you want
available to internal code (telemetry, framework internals) without them leaking into, say, a
debug dump of "everything in context":

```python
Context.add_hidden("internal_trace_id", "t-9")
Context.get_hidden("internal_trace_id")     # "t-9"
Context.has_hidden("internal_trace_id")     # True
"internal_trace_id" not in Context.all()    # True
```

## Scoping

`scope(**adds)` layers extra values on top of the current context for the duration of a `with`
block, then **restores the prior snapshot** on exit — even if the block raises:

```python
Context.add("tenant", "acme")

with Context.scope(tenant="beta", request_id="r-1"):
    Context.get("tenant")        # "beta"
    Context.get("request_id")    # "r-1"

Context.get("tenant")            # "acme" — restored
Context.has("request_id")        # False — restored
```

This is the idiom for "run this block as if these values were set, without permanently mutating
the outer context" — e.g. running a sub-task on behalf of a different tenant.

## Task isolation

Because `Context` is `contextvars`-backed, each `asyncio` **task** gets its own copy-on-write view
— setting a value inside one task never leaks into a sibling task running concurrently:

```python
async def handle(tenant: str) -> str:
    Context.add("tenant", tenant)
    await do_work()
    return Context.get("tenant")

results = await asyncio.gather(handle("a"), handle("b"), handle("c"))
# results == ["a", "b", "c"] — never cross-contaminated, even though all three ran concurrently
```

## Dehydrate / hydrate

When work crosses a process boundary — most notably being **queued as a job** — the ambient
context doesn't automatically follow. `dehydrate()`/`hydrate()` give you a serializable snapshot
(visible **and** hidden values) to carry across that boundary:

```python
payload = Context.dehydrate()     # {"visible": {...}, "hidden": {...}}
# ... serialize `payload`, enqueue it alongside the job ...

# on the worker side, before running the job:
Context.hydrate(payload)          # restores both visible and hidden state
```

Values you put in `Context` must be serializable by whatever you dehydrate with (the contract is
yours to keep — `msgspec`-encodable values are a safe default). This guarantees only the round-trip
contract; automatically threading dehydrate/hydrate through the queue's push and pop is planned
queue-integration work — until it lands, call them explicitly around an enqueue.

### Callbacks

Register a callback to run every time context is dehydrated or hydrated — useful for a service
provider that wants to inject/consume its own keys without every caller knowing about them:

```python
Context.dehydrating(lambda payload: payload["hidden"].setdefault("app_version", "1.4.0"))
Context.hydrated(lambda payload: configure_logger(payload["visible"].get("request_id")))
```

## Common mistakes & gotchas

- **Expecting `Context` to survive across a queued job automatically.** It won't — a job runs in a
  different process/worker with its own empty context. Use `dehydrate()`/`hydrate()` explicitly
  (or the queue integration once it wires this in).
- **Putting non-serializable values in context you intend to dehydrate.** `dehydrate()` doesn't
  validate that its values serialize — that surfaces later, at the point you actually try to
  serialize the payload.
- **Forgetting `scope()` restores hidden values too**, not just the keys you passed as `**adds`.

## See also

- [Queues & Jobs](queues.md) — where the dehydrate/hydrate contract gets consumed.
- [Telemetry](telemetry.md) — a natural home for hidden, framework-internal context.
