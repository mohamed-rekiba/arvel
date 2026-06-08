# Epic: `when_loaded` honors the eager-relation cache

## Summary
`JsonResource.when_loaded` silently dropped eager-loaded relations because it only checked
`resource.__dict__`, while Arvel's async relations cache eager results under
`__arvel_eager_relations__`. The documented `with_(rel)` → `when_loaded(rel)` pattern now
works for every relation type.

**Module:** http / resources · **Spec:** `docs/pipeline/specs/WI-arvel-005-when-loaded-eager-cache.md`

## Stories

### Story 1: Eager-loaded relations appear in resource output
**As an** API developer, **I want** `when_loaded("posts")` to include the relation after I
eager-load it with `with_("posts")`, **so that** my response carries the data I loaded
instead of silently omitting it.

**Acceptance Criteria**:
- [x] Given a model eager-loaded via `with_(rel)` (async relation: has-many/belongs-to-many/morph-to-many), when `when_loaded(rel)` runs, then it returns the loaded relation and the key appears in `to_dict` output.
- [x] Given no eager load and no committed relation, when `when_loaded(rel)` runs, then it returns the missing sentinel and the key is stripped — no lazy load is triggered.
- [x] Given a SQLAlchemy-committed relation on `__dict__`, when `when_loaded(rel)` runs, then it still resolves (no regression).

**Security Requirements**:
- [x] None — read-only serialization behavior; never triggers an unexpected query.

**Documentation Requirements**:
- [x] `docs/site/docs/the-basics/resources.md` note clarifies `when_loaded` covers both SQLAlchemy and Arvel async relations after `with_()`.

**Requirement Refs**: SPEC-1, SPEC-2, SPEC-3
**Priority**: Must · **Complexity**: Small · **Status**: Done

### Story 2: The fix respects the HTTP↔database layering rule
**As a** framework maintainer, **I want** the resource layer to stay free of an
`arvel.database` import, **so that** the deliberate decoupling (paginators via the
`Paginatable` Protocol) isn't broken by this fix.

**Acceptance Criteria**:
- [x] Given the fix, when inspecting `http/resources.py` imports, then there is no new `arvel.database` import — the eager cache is read by attribute name (the same contract `model.py` uses).

**Security Requirements**:
- [x] None.

**Documentation Requirements**:
- [x] A code comment documents the mirrored cache-attribute name and why it's read by name.

**Requirement Refs**: SPEC-4
**Priority**: Should · **Complexity**: Small · **Status**: Done

## Dependencies
- None. Independent of WI-arvel-001..004.

## Notes
- The kit doesn't wire `JsonResource` to any live endpoint (its `ProductResource` /
  `CategoryResource` are dead code), so this is a framework-correctness fix with no kit
  runtime impact — but it closes a real Laravel-parity gap (`whenLoaded`) and a silent
  data-loss bug against the documented contract.
- Deferred follow-ups (separate work items):
  - **F2** — `whenNotNull` / `whenAppended` / `with()` / `withoutWrapping()` parity gaps (additive API).
  - **F3** — no auto-resolution of a bare `JsonResource` controller return (documented design).
  - **F4** — `ResourceResponse` can't encode `datetime`/`Decimal`/UUID/ORM objects (encoder WI).
  - **F5** — `additional({"meta": ...})` replaces a paginator's `meta` wholesale (tested intentional).
  - **F6** — kit dead-code resources + divergent pagination envelopes (`pagination` vs `total`) (kit-cleanup WI).
  - **F7** — `schema` ClassVar not wired into FastAPI `response_model`.
