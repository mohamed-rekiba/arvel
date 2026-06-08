# WI-arvel-033 — Log redaction must recurse into nested dicts/lists

- **Module**: 33 — logging (`otel_logger._redact`)
- **Complexity**: L2
- **Risk tier**: 3 (A09 sensitive-data exposure; the redaction feature silently fails for nested context)
- **Data classification**: confidential
- **Status**: completed

## Problem

`otel_logger._redact` scrubbed only the **top-level** keys of a log line's
attributes:

```python
return {k: "[REDACTED]" if is_secret(k) else v for k, v in attrs.items()}
```

So any secret nested inside a dict or list value leaked verbatim, because the
top-level key isn't itself a secret:

```python
Log.info("login", payload={"password": "hunter2", "user": "alice"})
# emitted: payload={'password': 'hunter2', 'user': 'alice'}   ← leaked
Log.info("batch", items=[{"access_token": "T"}])
# emitted: items=({'access_token': 'T'},)                      ← leaked
```

Passing a dict/list as log context is common (`Log.info("event", body=request_body)`),
and OTel's log data model does allow nested map/sequence attribute values — so this
is a real exposure, not a theoretical one.

Two related inconsistencies made it worse:

- WI-019 deferred "nested-dict redaction (shallow by design)", but the code
  comment claimed the matcher "Mirrors `config._is_secret_key` so secret detection
  is consistent." `config._strip_secrets` (the partner of `_is_secret_key`) **is
  recursive** — so the comment promised behavior the function didn't deliver.

## Repro

```python
from arvel.facades import Log
from arvel.testing.observability import FakeObservability

with FakeObservability() as obs:
    Log.info("login", payload={"password": "hunter2"})
rec = next(r for r in obs.log_records if r.body == "login")
assert rec.attributes["payload"]["password"] == "[REDACTED]"  # FAILS before fix
```

## Fix

Make `_redact` walk dicts and lists to any depth, masking secret-keyed values
wherever they appear — mirroring `config._strip_secrets` (which drops; here we
mask, since logs keep the surrounding shape):

```python
def scrub(value: object) -> object:
    if isinstance(value, dict):
        items = cast("dict[object, object]", value)
        return {
            str(k): "[REDACTED]" if is_secret(str(k)) else scrub(v)
            for k, v in items.items()
        }
    if isinstance(value, list):
        return [scrub(item) for item in cast("list[object]", value)]
    return value

return cast("dict[str, Any]", scrub(attrs))
```

The substring secret-matching (`LOG_REDACT_FIELDS`, fail-closed default set) is
unchanged and now applies at every depth. The misleading comment is corrected to
reference `config._strip_secrets`.

## Acceptance criteria

- A secret key nested in a dict (any depth) or inside a list of dicts is
  `[REDACTED]`.
- Non-secret nested structures pass through unchanged.
- Top-level redaction and custom `LOG_REDACT_FIELDS` behaviour are preserved.
- ruff + format, mypy, pyright clean; observability suite green.

## Out of scope (reviewed, no change)

- `_inject_exception` logs `exception.message`/`exception.stacktrace` verbatim.
  Redacting free-form exception text would be lossy and is not key-based; left as-is.
- Hint-set divergence between `otel_logger._DEFAULT_REDACT_FIELDS` and
  `config._SECRET_HINTS` is intentional (log redaction vs cache stripping serve
  different surfaces); only the recursion behaviour is unified.

## Files

- `packages/arvel/src/arvel/logging/otel_logger.py` (`_redact` recurses; comment fixed)
- `packages/arvel/tests/observability/test_wi_033_log_redaction_nested.py` (new, 6 cases)

## Notes

Pre-existing, unrelated suite failure out of scope: `tests/observability/test_wi_030_config.py`
(cwd-dependent skeleton path, flagged since WI-arvel-030).
