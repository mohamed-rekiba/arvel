# Pagination

Lists are easy until they are not. Arvel gives you two complementary tools: **offset pagination** for simple UIs and **cursor pagination** for feeds that need stable performance as the table grows. Both ship as small, typed result types you can drop straight into JSON APIs.

## Why two styles?

Offset pagination answers "give me page 3 of the admin table." Cursor pagination answers "give me the next chunk after the item the client already saw." Offsets are straightforward but can get expensive at high page numbers; cursors stay predictable because each page starts after a known key.

Arvel does not hide that tradeoff — it gives you primitives and lets your controllers choose.

## Offset-based results

`PaginatedResult` bundles rows with metadata: total row count, current page, and page size. Construct it after you run a count query and a limited select (often through your repository or a dedicated service method).

```python
from arvel.data.pagination import PaginatedResult, MAX_PER_PAGE

per_page = min(requested_per_page, MAX_PER_PAGE)
offset = (page - 1) * per_page

items = await (
    Post.query(session)
    .order_by(Post.id)
    .limit(per_page)
    .offset(offset)
    .all()
)
total = await Post.query(session).where(...).count()

result = PaginatedResult(
    data=list(items),
    total=total,
    page=page,
    per_page=per_page,
)
payload = result.to_response()
```

`to_response()` returns a typed structure with `data` and `meta` — handy for serializers. `last_page` and `has_more` are derived properties on the dataclass, so you do not duplicate that math in every controller.

## Capping page size

`MAX_PER_PAGE` defaults to **100**. If a client asks for a thousand rows, `PaginatedResult` clamps `per_page` in `__post_init__` so a single request cannot accidentally DOS your database. You can still choose a smaller cap per endpoint if your payloads are heavy.

## Cursor-based pagination

Cursor flow is encode → filter → return next cursor. Arvel ships `encode_cursor` and `decode_cursor` so the wire format stays opaque: clients pass back a string token, not raw primary keys (though the token encodes field name and value).

```python
from arvel.data.pagination import CursorResult, encode_cursor, decode_cursor

# After fetching one page ordered by a stable column (e.g. id):
next_cursor = encode_cursor("id", last_row.id) if has_more else None

result = CursorResult(
    data=rows,
    next_cursor=next_cursor,
    has_more=has_more,
)
payload = result.to_response()
```

On the next request, decode the cursor, apply `Model.id > decoded_value` (or `<` for descending feeds), and `limit(per_page + 1)` to detect whether another page exists.

## Ordering discipline

Cursor pagination only works when ordering is **stable**. Use a unique column (often the primary key) or a documented composite. If two rows can tie on the sort key, the cursor can skip or duplicate — fix that in the schema or add a tie-breaker column.

## Choosing in practice

Use offset pagination for internal tools and small tables. Reach for cursors when you expose public APIs, infinite-scroll feeds, or any list that might grow without a bound. Arvel’s types keep the contract explicit; your job is to pick the ordering column and enforce `MAX_PER_PAGE` at the edge.
