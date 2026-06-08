# Epic: Collection intersect/diff compare by value

## Summary
`Collection.intersect` and `Collection.diff` must compare elements by value
(`==`), not object identity, so value-equal dicts, models, and runtime strings
match — consistent with `only`/`except_` and Laravel.

**Module:** support · **Spec:** `docs/pipeline/specs/WI-arvel-020-collection-value-equality.md`

## Stories

### Story 1: intersect/diff use value equality
**As a** developer using `Collection`, **I want** `intersect`/`diff` to match by
value, **so that** equal-but-distinct objects (dicts, models, runtime strings)
are compared correctly instead of by identity.

**Acceptance Criteria**:
- [x] Given value-equal dicts, when I call `intersect`/`diff`, then matches are by value.
- [x] Given runtime-built strings (not constant-folded), when I call `intersect`/`diff`, then matches are by value.
- [x] Given the same inputs, `intersect` agrees with `only` and `diff` agrees with `except_`.
- [x] Given plain `object()` members, existing behavior is preserved.

**Security Requirements**:
- [ ] None (internal data-structure helper).

**Documentation Requirements**:
- [x] `Collection.intersect`/`diff` docstrings state value-equality semantics.

**Requirement Refs**: SPEC-1 · **Priority**: Must · **Complexity**: Small · **Status**: Done

## Out of scope (deferred)
- `Str.limit` trailing-whitespace trim, `Str.slug` `@ → at` dictionary, `Arr.get`/`has` numeric-index traversal — minor parity, additive.
