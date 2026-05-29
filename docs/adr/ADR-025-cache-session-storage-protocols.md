# ADR-025 — Store/Driver interfaces as `typing.Protocol`, not ABC

**Status**: Accepted
**Date**: 2026-05-17
**Deciders**: Arvel core team

---

## Context

WI-006 introduces `CacheStore`, `SessionStore`, and `StorageDisk` as the interface contract for
all store/driver implementations. The choice is between `ABC` (abstract base class) and
`typing.Protocol`.

## Decision

All three interfaces are `typing.Protocol` (structural subtyping), not `ABC` (nominal subtyping).

## Rationale

1. **Third-party extensibility**: a third-party cache store doesn't need to `import arvel` to
   implement the protocol. Duck typing works at runtime; the type checker verifies compliance.
2. **Test isolation**: test stores (e.g., `SpyStore`) can be defined in a test file with no
   framework import, keeping the test boundary clean.
3. **`runtime_checkable`**: `isinstance(store, CacheStore)` works for the `TaggedCache` assertion.
4. **Consistency**: `HttpExceptionHandler` (WI-002) and `RateLimiterStore` (WI-002) both used
   `Protocol`-style contracts. This is the established Arvel pattern.

## Consequences

- Store implementations do NOT inherit from `CacheStore` / `SessionStore` / `StorageDisk`.
  They implement the methods with matching signatures.
- Type checkers verify protocol compliance at call sites (e.g., `CacheManager.store()` return type).
- Adding a required method to the protocol is a breaking change for all existing stores.
