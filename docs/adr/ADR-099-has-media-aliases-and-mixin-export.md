# ADR-099: `HasMedia` aliases and `HasMediaMixin` re-export

**Status**: Accepted
**Date**: 2026-05-24

## Context

`HasMedia` shipped with `add_media()` and `clear_media_collection()`. The e-commerce demo
expected `attach_media()` (one-call attach with collection name) and `delete_media()`. The name
mismatch led the demo to define its own `HasMediaMixin` instead of using the framework class.

## Decision

1. Add `attach_media(source, *, file_name, collection)` as a one-call alias that chains
   `add_media().to_media_collection(collection)`.
2. Add `delete_media(collection)` as an alias for `clear_media_collection(collection)`.
3. Export `HasMediaMixin = HasMedia` from `arvel_image/__init__.py`.

`add_media()` and `clear_media_collection()` are kept unchanged (existing callers unaffected).

## Consequences

- Positive: Demo's `HasMediaMixin` can be deleted; one canonical class in the framework.
- Positive: `attach_media()` is more ergonomic — single call vs. `add_media().to_media_collection()` chain.
- Negative: None. All three are additive.
