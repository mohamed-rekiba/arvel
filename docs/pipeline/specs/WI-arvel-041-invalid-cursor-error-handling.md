# WI-arvel-041 — Malformed pagination cursor surfaces as a 500 instead of a 400

- **Module:** 41 (ORM pagination — offset / simple / cursor)
- **Complexity:** L2
- **Risk tier:** 2
- **Data classification:** internal
- **Status:** completed

## Audit scope

The three paginators on `QueryBuilder` (`arvel/database/query.py`): `paginate`
(offset + `COUNT`), `simple_paginate` (offset, no total), and `cursor_paginate`
(keyset, bidirectional). Page/cursor resolution from the active request
(`resolve_page`, `resolve_cursor`), cursor encode/decode (`_encode_cursor`,
`_decode_cursor`), keyset WHERE construction (`_apply_keyset_where`), global-scope
interaction, and the paginator output envelopes (`to_dict` / `to_response`).

## Findings

The paginators themselves are sound and Laravel-aligned:

- `paginate` clamps `page` to `>= 1`, runs the `COUNT` on a subquery with ORDER BY
  stripped, and reports `total` / `last_page`. `simple_paginate` fetches
  `per_page + 1` and reports `has_more` without a count.
- `cursor_paginate` is keyset-based: it flips column directions for backward
  traversal then reverses the page, resets any pre-existing ORDER BY so the keyset
  ordering fully controls direction, and applies global scopes via
  `apply_global_scopes()`. Cursor tokens are opaque (base64 JSON), matching
  Laravel's contract.

**Defect (fixed): a malformed `?cursor=` token returns a 500.** `_decode_cursor`
raises `InvalidCursorError` (an `ORMError`) on any bad token — bad base64, bad
JSON, missing `_p`/`_n` keys, wrong types — and `cursor_paginate` re-raises it when
the keyset WHERE can't be built from the decoded params. A cursor is opaque client
input: a hand-edited, truncated, or stale token is *bad request* input, not a
server fault. But `InvalidCursorError` had no HTTP translator, so it fell through
to the catch-all and became a `500 INTERNAL_ERROR`. Worse, the un-translated path
risked leaking the base64/JSON decode reason (e.g. `Invalid base64-encoded
string: ...`) into the error message.

## Fix

Register an `InvalidCursorError` translator in `http_provider.default_translators`,
alongside the existing `ModelNotFoundError → 404` one:

```python
translators[InvalidCursorError] = lambda _exc: BadRequestException(
    "Invalid pagination cursor."
)
```

A fixed message is used on purpose — the decode internals never reach the client.
The provider already imports `arvel.database.exceptions` optionally, so this adds
no new import coupling; apps without the database package are unaffected.

## Tests

`packages/arvel/tests/http/test_wi061_model_not_found_404.py`:
- `test_provider_wires_invalid_cursor_to_400` — the default translator map wires
  `InvalidCursorError` to a `BadRequestException` with `status_code == 400`.
- `test_invalid_cursor_returns_400_without_leaking_decode_internals` — end-to-end
  through the `HttpExceptionHandler`: a raised `InvalidCursorError` produces a 400
  envelope with the fixed message, and the raw `base64` decode reason is absent
  from the response body.

## Deferred (parity-additive / separate items)

- None for offset/simple/cursor pagination. The paginator surface matches
  Laravel's `LengthAwarePaginator` / `Paginator` / `CursorPaginator` semantics.

## Gates

ruff check + format clean; mypy 0 issues (1065 files); pyright 0 errors / 0
warnings; pagination suite 82 passed; the `test_wi061` HTTP-translator file 11
passed (incl. the 2 new cursor cases).
