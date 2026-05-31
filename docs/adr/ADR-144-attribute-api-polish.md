# ADR-144: Attribute API polish bundle

Status: Accepted (delivered WI-arvel-025)

Eloquent-parity increment (backlog `006`, story S14) — the last of Epic 006. Fills in the remaining
model helper surface. No schema change.

## ADR-144-01: Per-instance appends

Status: Accepted

`append(*names)` adds accessor names to one instance's serialized output; `set_appends(list)`
replaces the per-instance list. Stored in a `_instance_appends` ClassVar slot (set via
`object.__setattr__`, like `_instance_hidden`) so it stays out of dataclass/ORM field processing.
`to_dict()` merges class-level `__appends__` with the per-instance list via `_collect_appends()`
(extracted to keep `to_dict` under the complexity gate).

## ADR-144-02: Conditional visibility

Status: Accepted

`make_hidden_if(condition, *fields)` / `make_visible_if(...)` apply the existing
`make_hidden`/`make_visible` only when `condition` holds. `condition` is a bool or a
`self`-predicate (`Callable[[model], bool]`), matching Laravel's bool-or-Closure form. Both return
`self` for chaining.

## ADR-144-03: `only` / `except_`

Status: Accepted

Subset helpers over `to_dict()`: `only(*keys)` keeps just those keys (missing ones skipped);
`except_(*keys)` drops them. `except_` is spelled with a trailing underscore — `except` is a Python
keyword.

## ADR-144-04: Key + column helpers

Status: Accepted

`get_key_name()` (classmethod) returns the single PK column name and raises on composite keys;
`get_key()` returns the PK value (a tuple for composite keys). `qualify_column(col)` prefixes the
table name (`"users.email"`), resolved from the mapper's local table. `is_same(other)` is true for
the same model type with the same non-null key; `is_not` is its inverse — Laravel's `is()`/`isNot()`.

## ADR-144-05: `discard_changes`

Status: Accepted

Reverts pending (dirty) column attributes back to their committed originals via SQLAlchemy's
`committed_state`, leaving the instance clean. Unflushed values with no committed original are left
as-is (nothing to revert to).

## ADR-144-06: `HasUuids` / `HasUlids` traits

Status: Accepted

Plain mixins (not `MappedAsDataclass` — they add no columns) that auto-fill an empty single-column
string PK on insert via a shared `before_insert` hook. The hook calls `type(target).new_unique_id()`
so each trait supplies its own generator: `HasUuids` → `uuid4`; `HasUlids` → a 26-char Crockford
base32 ULID (48-bit ms time + 80-bit `os.urandom`, sortable by the 10-char time prefix; randomness
within a single millisecond isn't monotonic, which is fine for keys). The model declares the PK as a
string column with `init=False, default=None` so it stays empty until the hook runs. `new_unique_id`
is a classmethod, overridable. A `_UniqueIdProvider` Protocol keeps the hook type-safe without
`Any`-widening.
