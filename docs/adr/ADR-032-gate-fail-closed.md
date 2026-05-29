# ADR-032: Gate Fail-Closed — Unregistered Ability → AuthorizationException

**Status**: Accepted
**Date**: 2026-05-17

## Context

When `Gate.authorize(ability, user, ...)` is called with an ability that has no registered closure or policy, two behaviors are possible: fail-open (allow the action) or fail-closed (deny the action).

## Options

| Option | Pros | Cons |
|---|---|---|
| A: Fail-open (allow unregistered) | No accidental lockouts during development | Security footgun: missing policy silently grants access |
| B: Fail-closed (deny unregistered) | Secure by default; missing policy is immediately visible | Developer must register every ability before using it |
| C: Configurable | Flexible | Complexity; two failure modes to document and test |

## Decision

**Option B** — Gate is fail-closed. Unregistered ability → `AuthorizationException`.

The OWASP A01 (Broken Access Control) risk is too high for fail-open. A typo in an ability name or a forgotten policy registration silently grants all users access to the resource. Fail-closed makes the bug immediately visible (403 in dev) rather than silently exploitable in production. This matches Laravel's behavior when using `Gate::authorize()` with no matching policy.

`Gate.allows()` returns `False` for unregistered abilities. `Gate.authorize()` raises `AuthorizationException`. This gives callers a way to gracefully handle missing policies when needed.

## Consequences

- **Gain**: Secure by default; missing policies are immediately visible failures
- **Accept**: Developers must register every ability explicitly; no "default allow"
- **Risk**: Accidental lockouts during development — mitigated by clear error messages from `AuthorizationException` (includes ability name and model class)
