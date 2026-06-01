# ADR-058: Re-entrant Event Suppression and Quiet Persistence

Status: Accepted

Eloquent-parity increment (backlog `006`, Sprint A: story S7). No HTTP or schema
surface — recorded as an ADR.

## ADR-058-01: Suppress events with a `ContextVar`, not a per-model flag

Status: Accepted

Laravel mutes its event dispatcher globally for `withoutEvents`. Arvel fires events
from async persistence methods (`save`, `delete`, `restore`, `force_delete`, plus
`create`), so suppression must survive `await` boundaries and stay isolated per
asyncio task. A module-level `ContextVar[bool]` does exactly that — each task/copy
sees its own suppression state, with no cross-task leakage that a class attribute or
plain global would cause under concurrency.

`without_events()` is an `@asynccontextmanager` that `set()`s the var and `reset()`s
it with the returned token on exit. Token reset (not `set(False)`) makes nesting
**re-entrant**: an inner block restores the outer block's `True`, and only the
outermost exit returns to `False`. `fire_async`, `fire_cancellable`, and
`fire_after_commit` early-return when the var is set — so cancellable before-hooks
can't abort a write inside the block either.

## ADR-058-02: `*_quietly` helpers wrap the existing methods in the context

Status: Accepted

`save_quietly`, `delete_quietly`, `force_delete_quietly`, `restore_quietly`, and
`update_quietly` are thin wrappers that run the normal persistence path inside
`without_events()`. No duplicated persistence logic — the quiet variants can't drift
from their loud counterparts. `update_quietly(**attrs)` fills then saves quietly,
mirroring Laravel's `updateQuietly` (Arvel has no separate instance `update`).
