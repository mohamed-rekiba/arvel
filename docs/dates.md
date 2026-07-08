# Dates

Dates are where quiet bugs hide: a naive `datetime` with no timezone, an hour that vanishes at a DST
boundary, a "2 minutes ago" that's awkward to write, a test that fails only at midnight. arvel's
`Date` is a timezone-aware date/time built on
[whenever](https://github.com/ariebovenberg/whenever) that closes those gaps — unambiguous about
time zones, correct across DST, easy to format, and **freezable in tests** so time-dependent code
is deterministic.

This page covers creating and parsing dates, arithmetic, comparing and formatting, the model casts,
and freezing time under test. `Date` is part of the **core** — nothing to install.

## Now, today, parse

```python
from arvel.dates import Date, now, today

Date.now()                 # current instant, tz-aware
Date.now("Europe/Berlin")  # in a specific zone
Date.today()               # start of today
Date.parse("2026-06-22T09:30:00+00:00")
```

`now()` and `today()` are module-level shortcuts for `Date.now()` / `Date.today()`.

## Arithmetic

Add or subtract calendar units by keyword:

```python
Date.now().add(days=7)            # one week from now
Date.now().subtract(hours=2)
Date.now().add(months=1, days=3)
Date.now().add_days(30)           # convenience for add(days=30)
```

Because the underlying engine is DST-aware, `add(days=1)` across a spring-forward boundary
gives you the same wall-clock time the next day — not "24 hours later." That correctness is the
reason `Date` exists instead of raw `datetime`.

## Period starts and differences

```python
d = Date.parse("2026-07-08T13:45:00+00:00[UTC]", "UTC")   # a Wednesday
d.start_of_day()                  # 2026-07-08 00:00
d.start_of_week()                 # 2026-07-06 00:00 (Monday)
d.start_of_month()                # 2026-07-01 00:00
d.start_of_year()                 # 2026-01-01 00:00

d.is_past()                       # relative to now (honors frozen test time)
d.is_future()
d.is_today()

a, b = Date.parse("2026-01-01T00:00:00+00:00[UTC]", "UTC"), Date.parse("2026-01-10T06:00:00+00:00[UTC]", "UTC")
a.diff_in_days(b)                 # whole calendar days from a to b, signed (future -> positive)
a.diff_in_hours(b)                # exact elapsed hours; also diff_in_minutes / diff_in_seconds
```

`diff_in_days` counts **calendar** days (a `.date()` difference), so it stays correct across DST;
the hour/minute/second diffs are exact elapsed time. `start_of_week` is Monday-based.

## Comparing and formatting

```python
Date.now().start_of_day()
Date.now().is_weekend()                # per config('app.weekend_days'); defaults to Sat/Sun
Date.now().is_weekday()                # the inverse
Date.now().to_iso()                    # "2026-06-22T09:30:00+00:00"
Date.now().diff_for_humans()           # "in 3 hours" / "2 days ago"
Date.parse(a) == Date.parse(b)         # value equality
Date.from_py(a_stdlib_datetime)        # wrap a stdlib datetime (e.g. a DB value) as a Date
```

### Weekend days

The weekend is **not** Saturday/Sunday everywhere — Egypt and much of the Gulf rest Friday/Saturday.
`is_weekend()` / `is_weekday()` read `config('app.weekend_days')`, a list of day names, and fall back
to Saturday/Sunday when unset:

```python
# config/app.py
weekend_days = ["friday", "saturday"]   # now Friday & Saturday count as the weekend
```

## Model casts

Cast a model attribute to `datetime` and it round-trips as a `Date` — stored as UTC ISO,
hydrated back into a `Date`:

```python
class Post(Model):
    __fields__ = {"published_at": str}
    __casts__ = {"published_at": "datetime"}

post.published_at            # a Date instance
post.published_at.add(days=1)
```

## Freezing time in tests

Deterministic tests need a fixed "now." `set_test_now` pins it; the freeze is stored in a
context variable, so it's **isolated per async test** — concurrent tests don't see each other's
frozen clock.

```python
from arvel.dates import Date

def test_expiry():
    Date.set_test_now(Date.parse("2026-01-01T00:00:00+00:00"))
    try:
        token = issue_token()              # uses Date.now() internally
        assert token.expires_at == Date.parse("2026-01-01T01:00:00+00:00")
    finally:
        Date.set_test_now(None)            # always release the freeze
```

## The Date facade

`Date` is also registered as a [facade](facades.md) (accessor `"date"`), so `Date.now()`,
`Date.today()`, and `Date.parse(...)` are reachable as a swappable container service — handy when
a service should resolve "the clock" rather than call the class directly.

## Common mistakes & gotchas

- **Reaching for stdlib `datetime`.** Mixing naive `datetime` with `Date` reintroduces the tz
  ambiguity `Date` exists to remove. Stay in `Date`; drop to `to_py()` only at a library
  boundary that demands a `datetime`.
- **Forgetting to release a freeze.** Always `set_test_now(None)` in a `finally` (or a fixture
  teardown) — a leaked freeze makes later tests mysteriously time-travel.
- **Assuming `add(days=1)` is `add(hours=24)`.** Across DST they differ — that's intentional.
  Use `hours=` when you mean elapsed time, `days=` when you mean the next calendar day.

## How it works

`Date` wraps a whenever `ZonedDateTime`. `now()` checks the per-context test-freeze first
(returning the frozen value when set) before reading the real clock, which is what makes time
travel isolated and deterministic. Arithmetic delegates to whenever, so DST and calendar rules
are the library's — arvel just provides the ergonomic surface and the cast integration.

## See also

- [Facades](facades.md) — the `Date` facade and faking it in tests.
- [Database & ORM](database/index.md) — the `datetime` cast.
- [Queues & Jobs](queues.md) — the scheduler ticks on wall-clock minutes.
