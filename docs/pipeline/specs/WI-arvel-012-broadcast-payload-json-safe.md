# WI-arvel-012 — Default broadcast payload must be JSON-safe

| | |
|---|---|
| **Module** | broadcasting |
| **Complexity** | L2 | **Risk** | Tier 2 | **Data** | internal |
| **Autonomous** | yes | **Frontend** | no |
| **Research** | `.context/research/012-broadcasting.md` (C1 fixed; auth presence/private discriminator, toOthers, Pusher auto-build deferred) |
| **Review** | C1 confirmed: every real driver json.dumps the payload, so a python-mode dump breaks the common event shape |

## Problem

`ShouldBroadcast.broadcast_with()` derived the default payload with python-mode dump:

```python
def broadcast_with(self) -> Mapping[str, object]:
    dump = getattr(self, "model_dump", None)
    if callable(dump):
        return _as_payload_mapping(dump())   # datetime/UUID/Decimal stay Python objects
    return {}
```

`RedisBroadcaster` and `PusherBroadcaster` both call `json.dumps(dict(payload))`.
A python-mode dump keeps `datetime`/`UUID`/`Decimal` as Python objects, so
`json.dumps` raises `TypeError`, wrapped as `BroadcastDriverError`. Broadcasting any
event carrying a timestamp/UUID/Decimal field — the common case — failed at send.

Reproduced: `OrderShipped(order_id: UUID, total: Decimal, shipped_at: datetime)` →
`json.dumps(...)` → "Object of type UUID is not JSON serializable".

## Spec Items → Verification

| ID | Spec item | Test | Status |
|---|---|---|---|
| SPEC-1 | An event with `datetime`/`UUID`/`Decimal` fields yields a JSON-safe default payload (ISO string / str / str). | `tests/broadcasting/test_should_broadcast.py::test_broadcast_with_is_json_safe_for_rich_types` | PASS |
| SPEC-2 | The default payload can be `json.dumps`'d without raising. | same test (`json.dumps(dict(payload))`) | PASS |
| SPEC-3 | Plain-typed events (int/str) are unchanged. | `...::test_default_broadcast_with_returns_model_dump_for_basemodel` (`{"order_id": 42}`) | PASS |
| SPEC-4 (X-cut: types/lint) | mypy `--strict` + pyright clean; ruff clean; broadcasting suite (91) + full framework suite (4304) green. | `mypy` + `pyright` + `ruff` + `pytest` | PASS |

## Root-cause fix

`should_broadcast.py` — `broadcast_with()` calls `dump(mode="json")` instead of
`dump()`. Pydantic's JSON mode serializes `datetime`→ISO, `UUID`→str, `Decimal`→str,
so the default payload is JSON-safe for every driver. Still routed through
`_as_payload_mapping` (str keys, Mapping guard).

## Deliberate design decisions

- **Fix at the source (the default derivation), not in each driver.** Drivers stay
  thin `json.dumps` calls; a developer who overrides `broadcast_with` with their own
  JSON-safe dict is unaffected.
- **`mode="json"` over a custom encoder** — Pydantic already owns the
  type→JSON mapping; no need for a bespoke `default=` hook.

## Deferred (tracked)

- **Auth presence/private discriminator** — `BroadcastAuthController` signs
  `channel_data` based on the callback returning a dict, not the `private-`/
  `presence-` channel-name prefix (Pusher decides by name). A private callback
  returning a dict yields a token the client can't reproduce.
- **`toOthers()`** — the event/auto-broadcast path doesn't thread `except_socket_id`.
- **Pusher driver** — not auto-buildable from `BroadcastConfig`; `body_md5` computed
  over `json.dumps(body)` may differ from httpx's wire serialization (signing parity).
