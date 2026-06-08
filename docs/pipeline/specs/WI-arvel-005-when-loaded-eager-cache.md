# WI-arvel-005 — `when_loaded` must honor Arvel's eager-relation cache

| | |
|---|---|
| **Module** | http / resources |
| **Complexity** | L2 | **Risk** | Tier 2 | **Data** | internal |
| **Autonomous** | yes | **Frontend** | no |
| **Research** | `.context/research/005-resources.md` (F1; reproduced empirically) |
| **Review** | defect confirmed by repro against a real `MorphToMany` eager load; F2–F7 deferred |

## Problem

`JsonResource.when_loaded(relation)` only checked `resource.__dict__[relation]`. Arvel's
async relations (has-many, belongs-to-many, morph-to-many, has-one-of-many, recursive) cache
eager results in a **separate** per-instance dict, `__dict__["__arvel_eager_relations__"]`
(see `database/orm/_eager.py`; `model.py:1122` reads the same key). So the **documented**
pattern — `with_("posts")` then `when_loaded("posts")` — silently dropped the relation from
the response, contradicting `docs/site/docs/the-basics/resources.md:156-157`.

Confirmed empirically: a `MorphToMany` eager-loaded via `with_("tags")` lands in
`__arvel_eager_relations__`, and the old `when_loaded("tags")` returned the missing sentinel.

## Spec Items → Verification

| ID | Spec item | Test | Status |
|---|---|---|---|
| SPEC-1 | After `with_(rel)`, `when_loaded(rel)` returns the eager-loaded relation (real model, async pivot), and the key appears in `to_dict` output. | `tests/http/test_wi005_when_loaded_eager.py::test_when_loaded_returns_eager_pivot` | PASS |
| SPEC-2 | Without an eager load (and no committed relation), `when_loaded(rel)` returns the missing sentinel and the key is stripped — no lazy load triggered. | `...::test_when_loaded_absent_without_eager_load` | PASS |
| SPEC-3 | SQLAlchemy committed relations on `__dict__` still resolve (no regression to the existing path). | `...::test_when_loaded_committed_dict_relation` + existing `test_044_framework_parity` | PASS |
| SPEC-4 (X-cut: layering) | No new import from `arvel.database` in `http/resources.py`; cache read by attribute name. | code review + `import` grep | PASS |
| SPEC-5 (X-cut: types/lint) | mypy --strict + pyright clean; ruff clean on changed files; full http suite green. | `mypy` + `pyright` + `ruff` + `pytest` | PASS |

## Root-cause fix

`http/resources.py` — `when_loaded`: after the `__dict__[relation]` check, also consult the
eager cache under `_EAGER_CACHE_ATTR = "__arvel_eager_relations__"` and return the cached
value. The constant is read by name (duck-typed), preserving the module's HTTP↔database
layering rule (the paginator path already avoids importing `arvel.database`).

## Deliberate design decisions

- Read the cache attribute by name instead of importing `get_eager_relation` — the module
  docstring mandates no `arvel.database` import; `model.py` accesses the same key the same way.
- Return the cached value as stored (a list for to-many relations). Iterable and consistent
  with the existing `__dict__` path; the developer maps it inside `to_dict` as before.

## Deferred (tracked)

- **F2** — `whenNotNull` / `whenAppended` / `with()` / `withoutWrapping()` parity gaps (additive).
- **F3** — no auto-resolution of a bare `JsonResource` controller return (documented design).
- **F4** — `ResourceResponse` can't encode `datetime`/`Decimal`/UUID/ORM objects (encoder WI).
- **F5** — `additional({"meta": ...})` replaces a paginator's `meta` wholesale (tested intentional).
- **F6** — kit `ProductResource`/`CategoryResource` are dead code; live paths use service
  formatters with divergent pagination envelopes (kit-cleanup WI).
- **F7** — `schema` ClassVar not wired into FastAPI `response_model`.
