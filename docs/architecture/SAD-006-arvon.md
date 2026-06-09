# SAD-006 — Arvon: fluent datetime layer

**Work Item**: WI-arvel-004 · **Status**: Approved (autonomous) · **Related**: [ADR-026](../adr/ADR-026-datetime-library.md), [PRD-001](../prd/PRD-001-arvon.md)

## Context

Arvel lacks a Carbon equivalent. This SAD defines how Arvon delivers a fluent,
immutable, timezone-aware datetime value type by wrapping `whenever`, and how it
integrates with the support layer, Pydantic, and the Arvent ORM.

## Component design

```
arvel.support.arvon
├── Arvon                 # value type + Carbon-style classmethod constructors,
│                         #   plus Pydantic hooks (__get_pydantic_core_schema__ /
│                         #   __get_pydantic_json_schema__) on the class itself
├── ArvonParseError       # typed parse failure
├── now() / today()       # module helpers (exported lazily from arvel.support)
└── freeze/travel/travel_back   # test-time clock via whenever.patch_current_time

arvel.database.model
└── "arvon" cast type     # opt-in cast → Arvon (UTC-coerced)
```

There is no separate `arvon_pydantic` module and no `_clock` variable — Pydantic support lives on the `Arvon` class, and the test clock is `whenever`'s own time patch.

### Decision 1 — Arvon is both value and constructor (no separate facade)

Like Carbon (`Carbon::now()` returns a `Carbon`), `Arvon` carries classmethod
constructors (`Arvon.now()`, `Arvon.today()`, `Arvon.parse()`, `Arvon.of()`,
`Arvon.from_timestamp()`, `Arvon.from_datetime()`) and returns `Arvon` instances. We do
**not** add a separate `arvel.facades.Arvon`: it would be redundant indirection over a
type that already self-constructs, and it would carry the `arvel.facades` 100% per-module
coverage burden for no behavioral gain. The `now()`/`today()` free functions in
`arvel.support` are the ergonomic sugar, mirroring Laravel's global `now()` helper.

### Decision 2 — Test-time clock via `whenever` patching (not container-bound)

`Arvon.now()` / `now()` / `today()` read the real UTC instant straight from
`whenever.ZonedDateTime.now("UTC")` — there's no custom `_clock` variable. For deterministic
tests, `Arvon.freeze(at)` (context manager) / `Arvon.travel(to)` / `Arvon.travel_back()` (and a
pytest fixture) swap the clock using `whenever.patch_current_time` — the Carbon `setTestNow`
model. This avoids container wiring and monkeypatching the wall clock. Freeze state is
process-local and test-only; it is never mutated on a request path.

### Decision 3 — Opt-in `arvon` ORM cast (surgical, not a global flip)

PRD FR-017/018 ask for `datetime`/`date` casts to return `Arvon`. Flipping the global
`datetime` cast would change the return type of **every** model datetime attribute across
the framework and the e-commerce kit, cascading into every `*Out` Pydantic model and JSON
serializer — a large, regression-prone change that violates surgical-change discipline.

Instead Arvon ships a dedicated **opt-in** cast: `__casts__ = {"published_at": "arvon"}`
returns an `Arvon` (UTC-coerced, same coercion as the existing `datetime` cast), and
serializes back through the existing write path. The default `datetime`/`date` casts are
unchanged. Models that want Arvon attributes opt in per field. A future epic may migrate
the global cast once every consumer is Arvon-aware; that migration is explicitly out of
scope here.

This means FR-018 (the `Timestamps` mixin returning `Arvon`) is delivered as "models may
cast `created_at`/`updated_at` to `arvon`", not a global mixin change. Recorded as a known
scope decision for Operations.

## API contract (public surface)

```python
class Arvon:
    # Construction
    @classmethod
    def now(cls) -> Arvon: ...
    @classmethod
    def today(cls) -> Arvon: ...
    @classmethod
    def of(cls, year: int, month: int, day: int, *, tz: str = "UTC") -> Arvon: ...
    #   date at midnight; chain .at(...) for a time. Raises ArvonParseError on impossible date.
    def at(self, hour: int, minute: int = 0, second: int = 0) -> Arvon: ...
    @classmethod
    def parse(cls, value: str) -> Arvon: ...          # ISO-8601; raises ArvonParseError
    @classmethod
    def from_timestamp(cls, value: float) -> Arvon: ...
    @classmethod
    def from_datetime(cls, value: datetime) -> Arvon: ...  # naive components treated as UTC

    # Arithmetic (immutable; each returns a new Arvon)
    def add_years(self, n: int) -> Arvon: ...
    def add_months(self, n: int) -> Arvon: ...        # clamps to last valid day
    def add_weeks(self, n: int) -> Arvon: ...
    def add_days(self, n: int) -> Arvon: ...
    def add_hours(self, n: int) -> Arvon: ...
    def add_minutes(self, n: int) -> Arvon: ...
    def add_seconds(self, n: int) -> Arvon: ...
    # sub_* counterparts for each unit

    # Comparison
    def eq/ne/gt/ge/lt/le(self, other: Arvon) -> bool   # plus dunders __eq__/__lt__/...
    @property
    def is_past(self) -> bool: ...
    @property
    def is_future(self) -> bool: ...
    def between(self, start: Arvon, end: Arvon, *, inclusive: bool = True) -> bool: ...

    # Boundaries
    def start_of(self, unit: Literal["day","week","month","year"]) -> Arvon: ...
    def end_of(self, unit: Literal["day","week","month","year"]) -> Arvon: ...

    # Timezone
    def in_timezone(self, tz: str) -> Arvon: ...

    # Humanize
    def diff_for_humans(self, other: Arvon | None = None) -> str: ...

    # Format / serialize / interop
    def to_iso8601(self) -> str: ...
    def to_date_string(self) -> str: ...              # "YYYY-MM-DD"
    def format(self, pattern: str) -> str: ...
    def to_datetime(self) -> datetime: ...            # aware stdlib datetime (UTC)

    # Test-time control
    @classmethod
    def freeze(cls, at: Arvon) -> AbstractContextManager[None]: ...
    @classmethod
    def travel(cls, to: Arvon) -> None: ...
    @classmethod
    def travel_back(cls) -> None: ...

def now() -> Arvon: ...
def today() -> Arvon: ...

class ArvonParseError(ValueError): ...   # typed, catchable; message is sanitized
```

### Pydantic integration

`Arvon` carries `__get_pydantic_core_schema__` (and `__get_pydantic_json_schema__`) so a
plain `field: Arvon` on a model validates from ISO-8601 strings / timestamps via
`Arvon.parse`/`from_timestamp` (invalid → `ValidationError` → 422), serializes via
`to_iso8601()`, and is documented in OpenAPI as `string` / `format: date-time`.

## Contracts note (no OpenAPI)

Arvon has **no HTTP surface** — it's an in-process value type. There is no
`docs/api/openapi.yaml` artifact for this work item; the API contract above is the
authoritative interface contract. (Hard-gate "contracts written" is satisfied by this
section; "OpenAPI" is N/A for a non-HTTP library feature.)

## STRIDE threat model

| Threat | Vector | Mitigation |
|---|---|---|
| **Spoofing** | n/a — no identity surface | — |
| **Tampering** | n/a — immutable value type, no shared mutable state on request paths | Immutability; freeze state is test-only |
| **Repudiation** | n/a — no audit-relevant actions | — |
| **Information disclosure** | Parse errors echoing internal library/stack details | `ArvonParseError` carries a sanitized message; no raw `whenever`/stdlib exception text or input echo beyond a short, safe summary |
| **Denial of service** | Adversarial date strings causing pathological parsing | Bounded parser: length cap on input before parse; rely on `whenever`'s linear ISO parser (no regex backtracking); reject early on oversized input |
| **Elevation of privilege** | n/a | — |

Security requirements SEC-001 (bounded parse), SEC-002 (fixed-catalogue humanize / validated
format), SEC-003 (freeze/travel test-only) trace here. Verified in Stage 4b.

## Dependencies

- **`whenever>=0.10.0`** — Rust-backed, cp314 wheels available (no build toolchain needed),
  `requires_python >=3.10`. Pre-1.0, so API churn is possible — the Arvon wrapper isolates it.

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| `whenever` pre-1.0 API churn | Low | Wrapper is the single seam |
| Global ORM cast regression | Medium | Avoided via opt-in `arvon` cast (Decision 3) |
| Parse DoS | Medium | Input length cap + non-backtracking parser (Stage 4b) |
