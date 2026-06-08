# Epic: Meilisearch filters render by value type

## Summary
The Meilisearch search engine must render `where()` filter values by type —
numbers and booleans bare so they match numeric/boolean fields, strings quoted
and escaped so a request-supplied value can't break out of the filter
expression. Previously every value was quoted as a string, so numeric/boolean
filters silently matched nothing and embedded quotes broke (or could rewrite)
the filter.

**Module:** arvel-search · **Spec:** `docs/pipeline/specs/WI-arvel-026-meilisearch-filter-typing.md`

## Stories

### Story 1: Numeric and boolean filters actually match
**As a** developer filtering a Meilisearch index, **I want** `where("price", 100)`
and `where("active", True)` to match numeric and boolean fields, **so that** my
faceted search returns the right results instead of nothing.

**Acceptance Criteria**:
- [ ] Given `where("price", 100)`, when the search runs, then the Meilisearch filter is `price = 100` (bare number).
- [ ] Given `where("active", True)`, when the search runs, then the filter is `active = true` (bare lowercase boolean, not `"True"`).
- [ ] Given `where("size", 4.5)`, then the filter is `size = 4.5`.
- [ ] Given `where("note", None)`, then the filter is `note IS NULL`.

**Security Requirements**:
- [ ] String filter values are quoted with `"` and `\` escaped, so a request-supplied value can't alter the filter expression.

**Documentation Requirements**:
- [ ] `docs/site/docs/packages/search.md` notes that `where` filters keep their type and strings are escaped.

**Requirement Refs**: C1a, C1b
**Priority**: Must · **Complexity**: Small · **Status**: Done
