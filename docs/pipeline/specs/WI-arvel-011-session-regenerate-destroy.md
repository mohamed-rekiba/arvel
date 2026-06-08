# WI-arvel-011 — Session regeneration must destroy the old store record

| | |
|---|---|
| **Module** | session |
| **Complexity** | L2 | **Risk** | Tier 3 | **Data** | internal |
| **Autonomous** | yes | **Frontend** | no |
| **Research** | `.context/research/011-sessions.md` (C1 fixed; cookie-driver integration / `invalidate()` / flash-shadowing deferred) |
| **Review** | C1 confirmed: `regenerate()` rotates the id but leaves the old session valid in the backend, contradicting the "prevent fixation" intent |

## Problem

`SessionData.regenerate()` swapped the in-memory `_session_id` to a fresh uuid but
never destroyed the old record, and `StartSession` had no `destroy` call at all:

```python
# data.py
def regenerate(self) -> None:
    self._data[_SESSION_ID] = uuid.uuid7().hex   # old id forgotten, never destroyed
```

`SessionGuard.login()` calls `regenerate()` "to prevent session fixation," but the
old session id stayed valid in the store with its pre-login payload until GC.
Laravel's auth login uses `migrate(true)`, which deletes the old session.

Reproduced: a guest request stores `cart` under id A; login regenerates to B; **A
remained in the store** holding `{cart: [...]}`. The auth marker is written only to
B (so account takeover is prevented), but the old session is not invalidated —
a defense-in-depth + data-leak + parity gap that contradicts the in-code comment.

## Spec Items → Verification

| ID | Spec item | Test | Status |
|---|---|---|---|
| SPEC-1 | `regenerate()` queues the previous id for destruction. | `tests/session/test_session_data.py::TestSessionDataRegenerate::test_regenerate_queues_old_id_for_destruction` | PASS |
| SPEC-2 | `drain_pending_destroy()` returns queued ids once, then is empty. | `...::test_drain_pending_destroy_is_one_shot` | PASS |
| SPEC-3 | The destroy queue is never serialized into the session payload. | `...::test_pending_destroy_not_serialized` | PASS |
| SPEC-4 | After regenerate through `StartSession`, the old store record is gone and the new id holds the data. | `tests/session/test_middleware.py::TestStartSessionMiddleware::test_regenerate_destroys_old_store_record` | PASS |
| SPEC-5 | Existing fixation test (`regenerate()` is called on login) and session persistence/flash tests still pass. | `tests/security/test_auth_safety.py` + `tests/session/` | PASS |
| SPEC-6 (X-cut: types/lint) | mypy `--strict` + pyright clean; ruff clean; full framework suite green (4303). | `mypy` + `pyright` + `ruff` + `pytest` | PASS |

## Root-cause fix

- `data.py` — `regenerate()` appends the current id to a new, non-serialized
  `_pending_destroy` list before assigning the new id; `drain_pending_destroy()`
  returns and clears it. `__init__` and `from_dict` both initialize the list;
  `to_dict()` is unaffected (the list lives outside `_data`).
- `middleware.py` — after writing the rotated session, `StartSession` destroys each
  queued old id: `for old in session.drain_pending_destroy(): await store.destroy(old)`.

## Deliberate design decisions

- **Always destroy on regenerate** (no `destroy=False` flag). The only caller is
  auth login, which wants Laravel's `migrate(true)` semantics; secure-by-default
  beats Laravel's non-destroying default for a greenfield framework.
- **Destroy in the middleware, after the write** — `SessionData` has no store
  reference; queuing + draining keeps the data object transport-agnostic and
  persists the new record before dropping the old one.
- **Cookie store `destroy` is a no-op**, so the change is safe across all drivers.

## Deferred (tracked)

- **Cookie driver ↔ StartSession integration** — `CookieStore.read_from_cookie` /
  `last_written_cookie` are unused by the middleware; the encrypted payload is never
  emitted on the standard path. Larger integration change.
- **`invalidate()`** — flush + new id + destroy old, as one call (additive parity).
- **Flash `get()` shadowing** — `get()` reads `_FLASH_OLD` before regular data, so a
  flashed key shadows a same-named persistent key (Minor).
- **`pull()`, `increment`/`decrement`, old-input helpers** — parity-additive.
