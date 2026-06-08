# WI-arvel-001 — ORM streaming must not silently drop eager loads

| | |
|---|---|
| **Module** | database / ORM |
| **Complexity** | L2 | **Risk** | Tier 2 | **Data** | internal |
| **Autonomous** | yes | **Frontend** | no |
| **Research** | `.context/research/001-database-orm.md` (F2) |
| **Review** | `requesting-code-review` — D1 confirmed blocking; `as_tree()` same defect |

## Problem

`QueryBuilder.stream()` (server-side cursor) and `RecursiveQueryBuilder.as_tree()`
ran without invoking the eager-load pipeline, so relations requested via `with_()`
were **silently dropped** — producing per-row N+1 queries, unpopulated relations, or
`LazyLoadingError` far from the cause. This violates Laravel's `cursor`/`lazy`
contract and the project's "no silent failure" rule.

## Spec Items → Verification

| ID | Spec item | Test | Status |
|---|---|---|---|
| SPEC-1 | `stream()` raises `EagerLoadNotStreamableError` when any eager load (async/pivot/morph/FK-method) is pending, naming the relations and pointing to `lazy`/`chunk`. | `test_stream_eager_load_guard.py::test_stream_rejects_fk_method_eager_load` | PASS |
| SPEC-2 | `stream()` also rejects SA `selectinload` eager loads (selectin does not load reliably under a server-side cursor — would leave relations empty). | `::test_stream_rejects_selectin_relationship` | PASS |
| SPEC-3 | `stream()` still streams correctly with no eager loads. | `::test_stream_without_eager_loads_yields_all_rows` + existing `test_streaming_completeness.py` | PASS |
| SPEC-4 | `RecursiveQueryBuilder.as_tree()` honors pending eager loads, mirroring its sibling `all()` (it materializes the full forest in memory). | `::test_as_tree_honors_eager_load_like_all` | PASS |
| SPEC-5 (X-cut: type safety) | mypy --strict + pyright clean; no new `# type: ignore`/`cast`/`Any` at public boundaries. | `uv run mypy` (1040 files) + `uv run pyright` | PASS (0 errors) |
| SPEC-6 (X-cut: no regression) | Full ORM suite stays green; ruff clean. | `pytest packages/arvel/tests/database` (1137 passed) + `ruff check` | PASS |
| SPEC-7 (X-cut: SQL/N+1) | No kit caller regressed; live kit catalog + soft-delete reads correct. | psql: 13 visible + 1 draft; 14 live products | PASS |

## Root-cause fixes

- `database/exceptions.py` — new `EagerLoadNotStreamableError` (public API).
- `database/query.py` — `stream()` fails fast via `_unstreamable_eager_relations()`
  (covers `_eager_loads`, `_async_eager`, `_tree_eager`, `_chaperones`);
  `RecursiveQueryBuilder.as_tree()` now calls `_eager_load_async` like `all()`.
- `database/__init__.py` — export `EagerLoadNotStreamableError`.

## Deliberate design decisions (documented divergence from Laravel)

- Laravel's `cursor()` silently can't eager-load (then lazy-loads → N+1). Arvel
  **fails fast** instead — strictly better, and aligned with the "no silent failure"
  rule. The streaming methods that *can* eager-load (`lazy`/`chunk`/`chunk_by_id`)
  are named in the error.

## Deferred (tracked, not silent-corrupting)

- `_Recursive` (`orm/relations.py`) builders from `node.descendants()` ignore
  arbitrary `with_()` eager loads (they use the `with_tree` cache model). Recorded
  as a follow-up parity item; not a silent data corruption on supported paths.
- `hasManyThrough`/`hasOneThrough` `with_()` eager integration; `$with` defaults;
  `preventLazyLoading` strict mode (research F5).
