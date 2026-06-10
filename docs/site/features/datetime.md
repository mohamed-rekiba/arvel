# Date & Time (Arvon)

<a name="introduction"></a>
## Introduction

`Arvon` is Arvel's fluent date and time type — the equivalent of Laravel's Carbon. It's an
immutable, timezone-aware value that wraps the [`whenever`](https://pypi.org/project/whenever/)
library, so every instance is stored against UTC by default and every transform returns a new
`Arvon` rather than mutating in place.

```python
from arvel.support import Arvon, now, today

now()                      # current instant (UTC)
today()                    # start of the current day
Arvon.of(2026, 6, 15)      # a date at midnight
Arvon.of(2026, 6, 15).at(9, 30)   # …with a time
```

`whenever` is only imported inside Arvon — application code never touches it directly.

<a name="quick-start"></a>
### Quick start

```python
from arvel.support import Arvon, now, today

expires = now().add_days(7)
deadline = Arvon.parse("2026-06-15T09:30:00Z")
assert deadline.is_future

# Deterministic tests
with Arvon.freeze(Arvon.of(2026, 6, 15).at(12, 0, 0)):
    assert now() == Arvon.of(2026, 6, 15).at(12, 0, 0)
```

| Need | API |
|---|---|
| Current instant / start of day | `now()` / `today()` |
| Parse user or API input | `Arvon.parse(iso_string)` — raises `ArvonParseError` |
| ORM datetime column as `Arvon` | `"arvon"` cast — see [ORM cast](#orm) |
| Pydantic request/response field | annotate as `Arvon` — see [Pydantic fields](#pydantic) |
| Freeze clock in tests | `Arvon.freeze(...)` or `Arvon.travel(...)` / `travel_back()` |

> [!WARNING]
> Every transform returns a **new** `Arvon`. Assign the result — `d.add_days(1)` does not mutate `d`.

<a name="construction"></a>
## Construction

| Call | Result |
|---|---|
| `Arvon.now()` / `now()` | current instant, UTC |
| `Arvon.today()` / `today()` | start of today |
| `Arvon.of(year, month, day, *, tz="UTC")` | a date at midnight |
| `.at(hour, minute=0, second=0)` | sets the time on an existing `Arvon` |
| `Arvon.parse(iso_string)` | parse ISO-8601 |
| `Arvon.from_timestamp(float)` | from a Unix timestamp |
| `Arvon.from_datetime(dt)` | from a stdlib `datetime` (naive → UTC) |

An impossible date (e.g. Feb 30) or malformed string raises `ArvonParseError`, a subclass of
`ValueError` you can catch. Parse errors carry a fixed, generic message and never echo the input.

<a name="arithmetic"></a>
## Arithmetic

Every `add_*` / `sub_*` returns a new value:

```python
expires = now().add_days(7)
earlier = expires.sub_hours(2)
```

Units: `years`, `months`, `weeks`, `days`, `hours`, `minutes`, `seconds`. Month and year math
clamps to the last valid day — `Arvon.of(2026, 1, 31).add_months(1)` lands on Feb 28.

<a name="comparison"></a>
## Comparison & boundaries

```python
d.is_past            # bool
d.is_future          # bool
a.between(start, end) # inclusive by default; pass inclusive=False to exclude ends
min(a, b, c)         # Arvon is orderable, so min/max work
d.start_of("week")   # Monday; also "day" | "month" | "year"
d.end_of("month")
```

<a name="humanize"></a>
## Humanize

```python
comment.created_at.diff_for_humans()   # "3 hours ago" / "in 2 days"
```

Pass another `Arvon` to change the reference point.

<a name="formatting"></a>
## Formatting & interop

```python
d.to_iso8601()                       # "2026-06-15T12:30:00Z"
d.to_date_string()                   # "2026-06-15"
d.format("YYYY-MM-DD hh:mm:ss")      # whenever's LDML-style pattern
d.to_datetime()                      # aware stdlib datetime (UTC)
```

<a name="pydantic"></a>
## Pydantic fields

Use `Arvon` directly as a field type. It validates ISO-8601 strings, timestamps, and
`datetime`s into `Arvon`, rejects garbage with a validation error, serializes to ISO-8601, and
reports `string($date-time)` in the JSON / OpenAPI schema.

```python
from pydantic import BaseModel
from arvel.support import Arvon

class Post(BaseModel):
    published_at: Arvon
```

<a name="orm"></a>
## ORM cast

Datetime columns keep their default `datetime` cast. Opt a column into `Arvon` with the
`arvon` cast:

```python
from typing import Any, ClassVar
from arvel.database import Model, id_

class Event(Model):
    __tablename__ = "events"
    id: int = id_()

    __casts__: ClassVar[dict[str, Any]] = {"happened_at": "arvon"}
```

`event.happened_at` now reads back as a UTC-coerced `Arvon` and serializes to ISO-8601 in
`to_dict()`. The cast is opt-in on purpose, so existing models are unaffected.

<a name="testing"></a>
## Testing — freezing time

`now()` and `today()` follow a freezable clock, so time-dependent code is deterministic:

```python
with Arvon.freeze(Arvon.of(2026, 6, 15).at(12, 0, 0)):
    assert now() == Arvon.of(2026, 6, 15).at(12, 0, 0)

# or, without a context manager:
Arvon.travel(Arvon.of(2030, 1, 1))
...
Arvon.travel_back()
```

Freeze/travel are test-only helpers and are not wired into any request path.
