# ADR-110: Session Guard Must Verify Password Before Login

**Status**: Accepted
**Date**: 2026-05-24

## Context

`SessionGuard.attempt()` logged users in after a successful email lookup without verifying
the submitted password against the stored hash. Any valid email address was sufficient to
authenticate.

## Decision

The guard calls `Hash.check(plain_password, stored_hash)` between `by_credentials()` and
`login()`. On mismatch it returns `False` without revealing whether the email existed.
The provider continues to do lookup only; password verification stays in the guard —
matching Laravel's exact responsibility split.

## Consequences

- Closes an authentication bypass (C-1 from May 2026 review)
- No API change — `attempt(credentials, request) -> bool` signature unchanged
- One-line change to `session.py`; covered by new test in `test_047_auth_security.py`
