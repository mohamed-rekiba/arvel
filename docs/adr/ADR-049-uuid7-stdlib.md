# ADR-049: Use uuid.uuid7 from stdlib Instead of Custom Implementation

**Date**: 2026-05-24
**Status**: Accepted

## Context

`arvel-ecommerce-demo/backend/app/models/base.py` contained a manual 32-line bit-twiddling
implementation of UUID v7 (timestamp-prefixed, RFC 9562). Python 3.14 ships `uuid.uuid7`
in the standard library, which is correct, RFC 9562 compliant, and monotonically sortable.

## Decision

Delete the custom implementation. Export `uuid7 = uuid.uuid7` from `app/models/base.py`
so all five model files that import `from app.models.base import uuid7` continue to work
without any changes to their `default_factory=uuid7` call sites.

## Consequences

- 32 lines of non-trivial bit manipulation removed from the codebase
- UUID generation is now handled by a stdlib function maintained by CPython
- `time`, `os` imports in `base.py` are removed (no longer needed)
- `import uuid` stays but `uuid.uuid7` is now a re-export rather than a replacement
