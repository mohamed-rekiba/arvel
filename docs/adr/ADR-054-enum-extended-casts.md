# ADR-054: Enum and extended built-in casts

Status: Accepted (delivered WI-arvel-017)

Eloquent-parity increment (backlog `006`, story S6). Extends the `__casts__` pipeline with
backed enums, `object`, `collection`, and `datetime:FORMAT`. No schema or route changes.

## ADR-054-01: An `Enum` subclass is a valid cast spec

Status: Accepted

`__casts__` already accepted a cast string or a `CastsAttributes` class/instance. We add a
third form: a Python `Enum` subclass passed directly (`"status": Status`). It resolves to a
`_ResolvedCast` where read returns the member (`Status(value)`), write stores the backing value
(`member.value`, or `Status(raw).value` for a raw input), and serialize emits the backing value.
Invalid values raise `ValueError` at write time — same fail-fast contract as the other casts.

We pass the enum **class** rather than a `"enum:Status"` string because Python has no global
class registry to resolve a name against, and a direct reference is type-checkable.

## ADR-054-02: `object` and `collection` are read-path-only, like `array`

Status: Accepted

`object` decodes JSON into a `SimpleNamespace` (attribute access); `collection` decodes into an
Arvel `Collection`. Both join `dict`/`list`/`array` in `_WRITE_SKIP_CASTS`: coercing to an
in-memory object on write would break INSERTs into a `String`/JSON column. The stored value
stays the raw assignment; the read transforms it.

Serialization can't leave a `Collection`/`SimpleNamespace` in `to_dict()` output, so both get a
built-in serializer (`_BUILTIN_SERIALIZERS`): `collection` → plain `list`, `object` → plain
`dict`. These run in `to_dict` after the read cast, matching Eloquent's `SerializesCastable`.

## ADR-054-03: `datetime:FORMAT` parses with a fallback and serializes with `strftime`

Status: Accepted

`"datetime:%Y-%m-%d %H:%M"` reads by trying `strptime(value, FORMAT)` first, falling back to the
shared ISO-8601 coercer (`_to_utc_datetime`) when the input doesn't match the format — so a DB
column holding ISO timestamps still hydrates. Naive results are pinned to UTC. Serialize emits
`dt.strftime(FORMAT)`. Write reuses the read coercer so assignment normalizes to a `datetime`.

## ADR-054-04: serialize skips `None`

Status: Accepted

`to_dict` previously called a cast's `serialize` for every listed key present in the row,
including unset (`None`) columns. The new built-in serializers (`list`, `strftime`) aren't
None-safe, so `to_dict` now skips serialize when the value is `None` — symmetric with the read
path, which already passes `None` through untouched.
