# ADR-036: Pagination HTTP + JSON parity

Status: Accepted (delivered WI-arvel-014)

Eloquent-parity increment (backlog `005`, story S9). Touches the HTTP middleware but adds no
new routes or schema — recorded as an ADR.

## ADR-036-01: Request resolution via a contextvar, not an HTTP import in the DB layer

Status: Accepted

Laravel resolves the current page/cursor from the global request. We don't want
`arvel.database` importing anything HTTP-specific, so the bridge is a contextvar:
`PaginationRequest(path, query)` lives in `arvel.database.paginator`, and
`ObservabilityMiddleware` sets it per request from the ASGI scope (`path` + parsed
`query_string`). The paginators call `resolve_page(page_name)`, `resolve_cursor(cursor_name)`,
and `resolve_path()` against it.

`paginate(per_page, page=None, page_name="page")` resolves the page when `page is None` (a
caller can still pin it explicitly). The path captured into the paginator at creation time is
used to build absolute links later.

## ADR-036-02: Two serialization shapes — `to_dict` (nested) and `to_response` (flat)

Status: Accepted

The existing `to_dict()` returns the project's `{data, meta, links}` nested envelope and stays.
`to_response()` is new and emits Laravel's **flat** envelope so ported API clients and
`JsonResource` consumers see the keys they expect:

- LengthAware: `current_page, data, first_page_url, from, last_page, last_page_url, links,
  next_page_url, path, per_page, prev_page_url, to, total`.
- Simple: same minus `total`/`last_page`/`links`.
- Cursor: `data, path, per_page, next_cursor, prev_cursor, next_page_url, prev_page_url`.

The `links` array is the windowed page list built from `on_each_side` (gaps rendered as
`"..."`) with the `&laquo; Previous` / `Next &raquo;` bookends and an `active` flag — byte-for-
byte the shape Laravel's `LengthAwarePaginator::toArray()` produces.

## ADR-036-03: `appends` / `with_query_string` / `fragment` are immutable chainables

Status: Accepted

`Paginator` is a frozen dataclass, so these return `dataclasses.replace` copies rather than
mutating. `appends(mapping)` adds query params carried on every URL; `with_query_string()`
pulls the current request's query (minus the page key) onto the paginator; `fragment(s)`
appends `#s`. The paginator owns the page key, so a request `?page=9` never leaks into the
generated `next`/`prev` URLs.

## ADR-036-04: Bidirectional cursors via a direction flag in the token

Status: Accepted

Cursor tokens become `base64(json({"_p": <keyset values>, "_n": <points_to_next>}))`. The
paginator emits **both** `next_cursor` and `prev_cursor`:

- Forward (no cursor or `_n=true`): order by the keyset, `WHERE keyset > cursor`, fetch
  `per_page + 1`. `next_cursor` if there's an overflow row; `prev_cursor` whenever we came
  from a prior page.
- Backward (`_n=false`): flip every column's direction, apply the inverse row-value
  comparison, fetch `per_page + 1`, then reverse the rows back to display order. A next page
  always exists (we walked back from it); `prev_cursor` only if there's an overflow row.

Because the user may have set their own `ORDER BY` before `cursor_paginate`, the method clears
ordering (`order_by(None)`) before applying the keyset order so direction is fully controlled.
Tokens stay opaque to callers; malformed tokens raise `InvalidCursorError`.
