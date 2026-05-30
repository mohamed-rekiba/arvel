# ADR-125: `hashed` Cast and Explicit Mass-Assignment Bypass

Status: Accepted

Eloquent-parity increment (backlog `006`, Sprint A: story S2). Touches credential
hashing → Risk Tier 3, so a Stage 4b security review accompanies it.

## ADR-125-01: `hashed` is a write-only cast over the existing `__casts__` dispatch

Status: Accepted

`__casts__` maps a column to one coercer applied on both read and write. A `hashed`
cast must hash on **write** and pass the stored digest through unchanged on **read**
(re-hashing a hash on every attribute access would corrupt it). So `hashed` joins
the dispatch table but is also added to a new `_READ_SKIP_CASTS` set — the mirror of
the existing `_WRITE_SKIP_CASTS` (read-only JSON casts). `__getattribute__` skips
read-skip casts; `__setattr__` applies them.

The coercer hashes via the project `Hash` facade (argon2id by default — never a weak
hash) and is **idempotent**: a value already shaped like an argon2 (`$argon2…`) or
bcrypt (`$2…`) digest passes through untouched, so re-saving a loaded model doesn't
double-hash.

## ADR-125-02: `force_fill` bypasses guards; `unguarded()` is a scoped context only

Status: Accepted

`force_fill(**attrs)` assigns every attribute through `__setattr__` (so mutators and
casts still run) without the `__fillable__`/`__guarded__` check — for trusted seed and
admin flows.

`Model.unguarded()` is a **synchronous, re-entrant context manager** backed by a
`ContextVar`; `_check_mass_assignment` early-returns while it's active. We deliberately
do **not** ship Laravel's global `unguard()` / `reguard()` toggle: an un-paired
`unguard()` silently disables mass-assignment protection process-wide, which directly
contradicts the security requirement that bypass be explicit and bounded. The scoped
context manager gives the same capability with guaranteed restoration.

Both bypasses are opt-in and must never wrap untrusted request data — enforced by
review, documented at the call sites.
