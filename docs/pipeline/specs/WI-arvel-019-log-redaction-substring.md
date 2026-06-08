# WI-arvel-019 — log redaction must match secret keys by substring

- **Module**: 19 — logging (`Log` facade / `OtelLogger`)
- **Complexity**: L2
- **Risk tier**: 3
- **Data classification**: confidential
- **Status**: completed

## Problem

`OtelLogger._redact` redacted a context field only when its lowercased name was
an **exact** member of the redact set. With the default hints (`password`,
`token`, `secret`, `authorization`, `api_key`, `private_key`), the most common
credential field names leaked to logs.

- **C1 (security, A09)** — `access_token`, `refresh_token`, `client_secret`,
  `api_secret`, `db_password`, `proxy_authorization`, etc. were emitted in
  cleartext. Inconsistent with `config._lookup_registry._is_secret_key`, which
  already matches the same hints by substring.

### Repro (pre-fix)

```python
_redact({"access_token": "AT", "client_secret": "CS", "db_password": "DP"})
# -> all three pass through unredacted
```

## Fix

`_redact` now redacts a field when any configured hint is a **substring** of its
lowercased name (mirrors `config._is_secret_key`). Fail-closed; tunable via
`LOG_REDACT_FIELDS`.

## Acceptance criteria

- `access_token` / `refresh_token` / `client_secret` / `api_secret` /
  `db_password` / `proxy_authorization` are redacted to `[REDACTED]`.
- Non-secret keys (`user_id`, `route`, `count`, `username`) pass through.
- A custom `LOG_REDACT_FIELDS` hint (e.g. `pin`) redacts `card_pin` by substring.
- Redaction runs on the real emit path via the `Log` facade.
- mypy --strict, pyright, ruff check, ruff format clean; full arvel suite green.

## Out of scope (deferred)

- Nested-dict redaction (only top-level context keys are scanned; documented as
  shallow).
- Log-level default divergence between `OtelLogger` (`debug`) and
  `ObservabilityConfig` (`info`) — the `debug` default is tested and matches
  Laravel; a design call, not a defect.

## Files

- `packages/arvel/src/arvel/logging/otel_logger.py`
- `packages/arvel/tests/observability/test_wi_019_log_redaction.py` (new)
- `docs/site/docs/features/logging.md`
