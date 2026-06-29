# Events

Events let you decouple "something happened" from "what to do about it." Instead of a
controller calling the mailer, the audit log, and the search indexer directly, it **dispatches
an event**; independent **listeners** react. Adding a new reaction later means adding a
listener — not editing the controller.

This page covers when to reach for events, dispatching and listening (string and typed class
events), the `until`/transactional variations, and how it all works. Events are part of the
**core** — nothing to install.

## When to use events

- A single action has **several side effects** that don't belong together (a user registers →
  send a welcome email, provision a workspace, notify the team).
- You want to **defer work** to the queue (send the email in the background).
- A package needs a **hook** into your app without you wiring it by hand.

If there's exactly one reaction and it's intrinsic to the action, just call it — an event adds
indirection you don't need.

## Dispatching and listening

Register a listener, then dispatch. A listener is any callable (sync or async):

```python
from arvel.events import Dispatcher

events = Dispatcher()

async def send_welcome(event):
    await Mail.to(event.user).send(WelcomeMail())

events.listen("user.registered", send_welcome)

await events.dispatch("user.registered", payload)
```

In an app you reach the shared dispatcher through the `Event` facade instead of constructing
one:

```python
from arvel import Event

Event.listen("user.registered", send_welcome)
await Event.dispatch("user.registered", user)
```

## Class events (recommended)

A string works, but a small event class documents the payload and gives listeners a typed
object:

```python
from dataclasses import dataclass

@dataclass
class UserRegistered:
    user: User

Event.listen(UserRegistered, send_welcome)
await Event.dispatch(UserRegistered(user=user))
```

An event is just a class — a `@dataclass` is convenient, but any object works; its **type** is the
channel.

The event's **type** is the channel — listeners registered for `UserRegistered` receive every
`UserRegistered` instance.

## Worked example: fan-out

```python
def index_user(event):       SearchIndex.add(event.user)
def audit(event):            AuditLog.record("registered", event.user.id)

Event.listen(UserRegistered, send_welcome)   # async
Event.listen(UserRegistered, index_user)     # sync
Event.listen(UserRegistered, audit)          # sync

await Event.dispatch(UserRegistered(user=user))
# → all three run; async listeners are awaited, sync ones called directly
```

## Variations

### Halting — `until`
Stop at the first listener that returns a non-`None` value and return it (useful for "can this
proceed?" checks):

```python
result = await Event.until("payment.authorize", order)
# returns the first listener's non-None result; later listeners don't run
```

A listener that returns `False` **stops propagation** without being the return value — a veto.
Model lifecycle hooks (`saving`, `deleting`) use this: return `False` to cancel the save.

### Wildcards
Subscribe to a family of string events with `*`:

```python
Event.listen("order.*", log_order_activity)   # order.placed, order.shipped, order.refunded …
```

### Checking & deferring
Ask whether anyone is listening (honors wildcards; accepts a class, string, or instance), and
**defer** events to fire later in a batch:

```python
Event.has_listeners(UserRegistered)      # True / False
Event.has_listeners("order.placed")

Event.push("report.ready", report)       # registered, not fired yet
await Event.flush("report.ready")        # dispatches everything pushed under this name (then drains)
Event.forget_pushed()                    # discard anything still pending
```

### Queued listeners — `ShouldQueue`
Mark a listener class with `ShouldQueue` and it runs on the queue instead of inline (when a
queue is bound), so the dispatch returns immediately:

```python
from arvel.events import ShouldQueue

class SendWelcome(ShouldQueue):
    async def handle(self, event): ...
```

### After-commit events — `ShouldDispatchAfterCommit`
An event marked `ShouldDispatchAfterCommit` (or dispatched inside `dispatcher.transaction()`)
is **buffered until the surrounding DB transaction commits**, and dropped if it rolls back — so
you never email a user about a record that was rolled back:

```python
async with events.transaction():
    await repo.save(user)                       # if this commits …
    await events.dispatch(UserRegistered(user)) # … the event fires; if it rolls back, it doesn't
```

## Model observers

A model fires lifecycle events — `saving`, `saved`, `deleted`, `restored` — and an **observer** groups
their handlers for one model in a class (Laravel `Model::observe`). Register it from a provider's
`boot()`:

```python
class PostObserver:
    async def saving(self, post):    # return False to cancel the save
        post.slug = slugify(post.title)
    async def saved(self, post): ...
    async def deleted(self, post): ...

Post.observe(PostObserver())         # scaffold one with `make:observer`
```

Each method runs when `Post` fires the matching event; only the hooks you define are wired.

## Common mistakes & gotchas

- **Listening with a string but dispatching a class (or vice-versa).** The channel must match:
  register and dispatch the *same* key — both the string `"user.registered"` or both the class
  `UserRegistered`.
- **Expecting a queued listener to run inline in tests.** `ShouldQueue` listeners only enqueue
  when a queue is bound; with no queue they run inline. In tests, swap a `FakeQueue` and assert
  with `assert_pushed`.
- **Side effects before commit.** If a listener emails or calls an external API and the
  transaction later rolls back, you've acted on data that doesn't exist — use
  `ShouldDispatchAfterCommit`.
- **A throwing listener aborts the rest.** Dispatch runs listeners in order; an unhandled
  exception propagates. Keep listeners defensive, or move risky work onto the queue.

## How it works

The `Dispatcher` keeps two maps: exact channels (string or class) → listeners, and wildcard
patterns → listeners. On `dispatch`, it resolves the channel (a class event also matches its
type), gathers exact + matching-wildcard listeners, and runs them in registration order —
`await`-ing coroutines, calling sync listeners directly. `until` returns early on the first
non-`None`; a `False` return breaks the chain. Class listeners are resolved through the
container, so their constructor dependencies are injected. It's a custom dispatcher by design
(no external engine) — small, synchronous-friendly, and queue/broadcast aware.

## See also

- [Queues & Jobs](queues.md) — where `ShouldQueue` listeners run.
- [Validation](validation.md) · [Authentication](auth/index.md)
