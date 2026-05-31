# ADR-145: Morph map foundation

Status: Accepted (delivered WI-arvel-025+1 / WI-arvel-026)

Supersedes the unqualified-class-name default of ADR-022 for the polymorphic `{name}_type` token.
First story of Epic 007 (relationship parity).

## Context

ADR-022 stored the owner's *unqualified class name* (`"Post"`) in the morph discriminator column.
That token is tied to the class name and its position in the import graph — rename `Post`, move it
to another package, and every stored `{name}_type` value silently stops resolving. Laravel solved
this with `Relation::morphMap()`: an explicit, stable alias per model.

## ADR-145-01: Process-global morph map

Status: Accepted

`morph_map({"post": Post, "video": Video})` registers alias→class entries (merge by default;
`merge=False` replaces). Called bare, `morph_map()` returns the current map. State lives in a single
module-level `_MorphState` instance mutated in place (no `global` rebinds, keeps `ruff PLW0603`
happy). It's process-global, matching Laravel — register once at boot. Tests reset it via
`reset_morph_map()` wired into the autouse `reset_global_state` fixture.

## ADR-145-02: Token resolution, both directions

Status: Accepted

- `get_morph_alias(cls)` (write side): the mapped alias if `cls` is in the map, else the short class
  name (the ADR-022 default — so unmapped apps behave exactly as before).
- `resolve_morph_class(alias)` (read side, for MorphTo in Story 2): the mapped class, else a fallback
  scan of `Model.registry.mappers` by short class name. Raises `MorphMapError` when nothing matches.
- `Model.get_morph_class()` is the public classmethod form of `get_morph_alias(cls)`.

All existing morph write/read paths (`MorphOne`/`MorphMany` create + query, `MorphToMany` pivot
ops, the query-builder morph-existence subquery) now route the token through `get_morph_alias` so a
registered alias is used consistently on both write and read. Unmapped models keep storing the short
name, so `test_morph.py` / `test_morph_to_many.py` pass unchanged.

## ADR-145-03: Strict mode

Status: Accepted

`require_morph_map(True)` flips strict mode: `get_morph_alias` (and therefore any polymorphic write)
raises `MorphMapError` for an unmapped model instead of falling back to the class name. Apps that
want refactor-proof tokens enforced everywhere turn this on at boot. Off by default.

## Migration note

Apps already storing short class names need no migration — that's still the unmapped default. Apps
adopting aliases should backfill existing `{name}_type` values from the old class name to the new
alias in a one-off migration, then call `morph_map(...)` (and optionally `require_morph_map()`) at
boot before any polymorphic write.
