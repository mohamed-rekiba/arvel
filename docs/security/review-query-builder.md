# Security Review — Query Builder

Area: ORM query construction, parameterization, and raw query escape paths.

## Scope

Active Record query builder, `select_raw` / `where_raw` raw-fragment helpers, CTE
construction, and the `literal_column` escape hatch.

## Findings

No critical or high findings. All user-controlled values pass through SQLAlchemy's
parameterization layer. `select_raw` and `where_raw` accept only developer-supplied string
literals — no user input flows into raw fragments in the current codebase.

## Controls Verified

- All `where()` conditions use bound parameters
- `select_raw` / `where_raw` callers audited — no user data interpolated
- `literal_column` used only with string constants from source code
- ORM-level soft-delete scopes enforced before raw fragment injection

## Next Review

Revisit when adding dynamic filter expressions driven by API query params.
