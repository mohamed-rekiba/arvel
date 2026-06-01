# ADR-059: Static event registration + custom event objects

Status: Accepted (delivered WI-arvel-020)

Eloquent-parity increment (backlog `006`, story S9). Adds three ways to wire model lifecycle
hooks without authoring a full observer class. No schema or route changes.

## ADR-059-01: `Model.on(event, callback)` wraps the observer machinery

Status: Accepted

Laravel exposes `Model::created(fn)`, `Model::saving(fn)`, etc. We collapse these to a single
`Model.on("created", cb)` classmethod. Rather than introduce a parallel callback registry, `on`
wraps the callable in a one-event `_CallbackObserver` and appends it to the same observer list
`Model.observe(...)` uses. So callbacks and observer-class methods run through the identical
dispatch path: cancellable before-hooks (`creating`/`updating`/`deleting`/`restoring`) honor a
`False` return, and async callables are awaited. One code path, no second dispatch loop to keep
in sync.

```python
User.on("created", lambda u: log.info("created %s", u.id))
User.on("creating", lambda u: False)  # aborts the insert
```

## ADR-059-02: `__dispatches_events__` maps lifecycle names to bus events

Status: Accepted

`__dispatches_events__ = {"created": UserCreated}` dispatches a custom event object on the app
event bus (the `Event` facade) when that lifecycle fires — Eloquent's `$dispatchesEvents`. The
mapped class subclasses `ModelEvent`, a frozen Pydantic `Event` with `arbitrary_types_allowed`
carrying the model instance under `.model`. Dispatch happens after the observer loop in both
`fire_async` and `fire_cancellable`.

When no dispatcher is bound (pure-DB unit tests with no `EventServiceProvider`), dispatch is
**silently skipped** rather than raising `FacadeNotBoundError`. Model persistence shouldn't hard
-depend on the event subsystem being booted; the mapping is an opt-in integration, not a
requirement.

## ADR-059-03: `__observed_by__` auto-registers at class-definition time

Status: Accepted

`__observed_by__ = [AuditObserver]` registers each observer in `Model.__init_subclass__`, the
Python equivalent of Laravel's `#[ObservedBy(...)]` attribute. It reads from `cls.__dict__`
(not inherited) so a subclass declaring its own list doesn't double-register a parent's
observers. Registration reuses `bind_observer`, so container-resolved observers and no-arg
observers behave exactly as with an explicit `observe()` call.

## ADR-059-04: `ModelEvent` is defined directly, not via a factory

Status: Accepted

An earlier draft built `ModelEvent` lazily through a factory function to avoid importing pydantic
at `events.py` import time. That made `ModelEvent`'s static type `Any`, which blocks
`class UserCreated(ModelEvent)` under strict type checking ("cannot subclass Any"). Since
`arvel.events.event` only pulls in pydantic (no database import — no cycle), `ModelEvent` is now a
plain top-level class. Subclassing type-checks, and the registry auto-registration in
`Event.__init_subclass__` still fires.
