# Epic: Config dict lookups are key-only (no method shadowing)

## Summary
Dotted config lookups into dict values must resolve by key only. A missing key
that shares a name with a dict builtin (`get`, `items`, `keys`, `values`, ...)
must miss — returning the supplied default (`config`) or raising `ConfigKeyError`
(`lookup`) — never the bound method.

**Module:** config · **Spec:** `docs/pipeline/specs/WI-arvel-018-config-dict-key-shadowing.md`

## Stories

### Story 1: Missing dict keys honor the default
**As a** developer reading config, **I want** `config("a.b.c", default)` to return
the default whenever `c` is absent, **so that** a key name colliding with a dict
method never silently yields a callable.

**Acceptance Criteria**:
- [x] Given a dict config node, when I read a missing key named like a dict builtin (`get`/`items`/`keys`/`values`/`pop`/`popitem`/`copy`/`update`/`clear`/`setdefault`/`fromkeys`), then `config(...)` returns the default and the result is not callable.
- [x] Given the same key, when I call `lookup(...)`, then `ConfigKeyError` is raised.
- [x] Given a real nested dict key, when I read it, then its value resolves unchanged (`cache.stores.redis.host`).
- [x] Given a namespace/module entry, when I read a dotted attribute path, then attribute access still resolves at any depth.

**Security Requirements**:
- [ ] None (internal config-access contract). Secret redaction in `config:cache` is unchanged.

**Documentation Requirements**:
- [x] `docs/site/docs/core-concepts/configuration.md` notes dict segments are key-only.

**Requirement Refs**: SPEC-1 · **Priority**: Must · **Complexity**: Small · **Status**: Done

## Out of scope (deferred)
- URL-embedded credentials in cached config are not redacted (documented limitation).
- No array-set form of `config()`; runtime config is read-only.
- `env()` type-driven coercion vs Laravel string coercion (deliberate).
