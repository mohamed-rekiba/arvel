# WI-arvel-032 — Raw model returns leak `__hidden__` columns through the HTTP layer

- **Module**: 32 — ORM serialization boundary (model `to_dict`/`__hidden__` vs. the Router response path)
- **Complexity**: L2
- **Risk tier**: 3 (A01 broken access control / A09 sensitive data exposure on the response path)
- **Data classification**: confidential
- **Status**: completed

## Problem

`Model.to_dict()` honours `__hidden__` / `__visible__` (and per-instance
`make_hidden`). But an Arvel `Model` is a `MappedAsDataclass`, so when a route
handler does the Laravel-idiomatic `return user`, FastAPI's `jsonable_encoder`
serialises it as a **plain dataclass** — every mapped column, including ones the
model marks `__hidden__`. A `password_hash`, `remember_token`, or API token would
ship straight to the client.

Laravel's `return $user;` runs the model through `toArray()`, which applies
`$hidden`. Arvel diverged: `to_dict()` was correct, but nothing routed bare model
returns through it.

```python
w = Widget(name="pub", secret="TOPSECRET")  # __hidden__ = ["secret"]
w.to_dict()                       # {"id": ..., "name": "pub"}        ✅ hidden honoured
jsonable_encoder(w)               # {"id": ..., "name": "pub",
                                  #  "secret": "TOPSECRET"}            ❌ leak
```

The framework's own routes and the ecommerce kit are **not** affected: they all
return Pydantic instances / `JsonResource` / explicit `response_model`, where the
schema is the output allowlist. The leak is a sharp footgun for any app route
that returns a raw model without a schema.

## Fix

A return-value normaliser in `Router.register_with_app`. When a route has **no
explicit `response_model`**, the handler is wrapped so its result is coerced
before FastAPI encodes it:

- a returned `Model` → `model.to_dict()` (honours hidden/visible/appends)
- a returned `list` containing models → each model → `to_dict()`, others untouched
- everything else (dict, Pydantic model, `Response`, primitives) → passed through

`to_dict()` only reads mapped columns, so no async relation load happens at
response time. The wrapper preserves the handler's `__signature__`, so FastAPI's
parameter/dependency resolution is unchanged.

Two independent safety margins keep this from touching existing behaviour:

1. **Type gate** — only raw `Model` (or lists of them) are converted; the kit /
   framework return Pydantic instances, so they pass straight through.
2. **`response_model` gate** — routes that opted into a schema control their own
   output and are left entirely to FastAPI.

## Acceptance criteria

- A route returning a raw model omits `__hidden__` columns from the JSON body.
- A route returning a list of models honours hidden on every element.
- Routes returning dicts / Pydantic models / `Response` objects are byte-for-byte
  unchanged.
- Routes with an explicit `response_model` are untouched.
- ruff + format, mypy, pyright clean; full suite green (only the two known
  pre-existing failures remain).

## Out of scope (reviewed, no change)

- **Mass assignment** (`__fillable__` / `__guarded__`): `create`, `fill`,
  `update_quietly`, `first_or_create`, `update_or_create` all route through the
  guard. Arvel is insecure-by-default (no fillable/guarded ⇒ all columns
  assignable), unlike Laravel's `$guarded = ['*']`. That's a deliberate design
  stance, not a bug — flipping it would break every model and is a separate
  decision.
- **Casts / mutators**: read (`__getattribute__`) and write (`__setattr__`) are
  symmetric; built-in enum/encrypted/datetime casts apply `serialize` on top of
  the read value consistently. No defect.
- **Nested models inside a returned dict** (`return {"user": user}`) still encode
  via FastAPI and would leak. Idiomatic responses use a resource/schema; a
  recursive encoder is heavier than this footgun warrants. Tracked as a follow-up,
  not fixed here.

## Files

- `packages/arvel/src/arvel/routing.py` (`_coerce_models_in_result`,
  `_wrap_response_normalizer`, wired into `register_with_app`)
- `packages/arvel/tests/routing/test_wi054_hidden_field_leak.py` (new)

## Notes

One pre-existing suite failure is unrelated and out of scope:
`tests/hardening/test_nosec_annotations.py` (bare `# nosec` codes in untouched
`console/_venv.py`, flagged since WI-arvel-031).
