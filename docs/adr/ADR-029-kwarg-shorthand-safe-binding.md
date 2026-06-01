# ADR-029 — Kwarg-shorthand `where(col=value)` binds parameters via `getattr`, never string SQL

**Status**: Accepted
**Date**: 2026-05-17

## Context

Eloquent's loose form (`User::where('email', $email)`) is convenient. Django's
`User.objects.filter(email=email)` is more convenient. Both have produced SQLi
bugs in the wild when implementers got lazy and string-concatenated the column
name into the SQL fragment.

Three options for the kwarg-shorthand path:

| Option | Pros | Cons |
|---|---|---|
| A. Reject kwarg-shorthand entirely — column-expression only | Eliminates the SQLi class | Fights Eloquent muscle memory; ugly for ad-hoc filters |
| B. Accept kwarg-shorthand but f-string the column name into the SQL | Convenient | **Critical** SQLi vector if a user's column name comes from external input |
| C. **Accept kwarg-shorthand; resolve `getattr(model, key)` to a typed `InstrumentedAttribute`** | Convenient AND safe | Slightly more work in the builder; raises `AttributeError` at call time on unknown columns |

## Decision

Option C. The implementation:

```python
def where(self, *clauses: ColumnElement, **kwargs: Any) -> Self:
    new = self._clone()
    for clause in clauses:
        new._where_clauses.append(clause)
    for key, value in kwargs.items():
        col = getattr(self._model, key)        # AttributeError if unknown
        if not isinstance(col, InstrumentedAttribute):
            raise AttributeError(f"{self._model.__name__}.{key} is not a column")
        new._where_clauses.append(col == value)
    return new
```

Same rule applies to `where_in`, `where_between`, `or_where`, `having`,
`group_by`, `order_by`, `pluck`, `value`. Any place a column name might be
named-by-string must route through `getattr`.

## Consequences

**Positive**:
- SQLi vector closed at the type-system level — `getattr` returns a Python
  attribute, not a string fragment.
- Unknown columns fail loudly at call time, not at query execution.
- The implementation is small (one `getattr` per kwarg).

**Negative**:
- Users who genuinely need to filter by a dynamic column name must use
  `getattr(Model, dynamic_name)` themselves, not the kwarg form. The DX docs
  document this with a security callout.

**Enforcement**:
- `tests/security/test_query_safety.py` covers every query-builder method
  with attacker-controlled values and column names.
- Stage 4b SQLi sweep is the centerpiece security gate for WI-003.
- Code review checklist: "Does this method accept a column name as a string
  and pass it through anywhere other than `getattr`?" → reject.
