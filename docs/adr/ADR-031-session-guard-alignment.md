# ADR-031: SessionGuard Alignment to Arvel SessionData

**Status**: Accepted
**Date**: 2026-05-17

## Context

The existing `SessionGuard`  reads `request.session` — Starlette's built-in dict-based session, populated by Starlette's `SessionMiddleware`. Arvel shipped its own session stack in : `StartSession` middleware populates `request.state.session` as a typed `SessionData` object. The two session systems can't safely coexist on the same route — one or the other must own session storage.

## Options

| Option | Pros | Cons |
|---|---|---|
| A: Keep `request.session` (Starlette dict) | No breaking change for WI-002 users | Two session systems coexist; Arvel's typed session is ignored by the guard; session fixation prevention is hard |
| B: Migrate to `request.state.session` (Arvel `SessionData`) | Single, typed session system; proper session fixation support; flash bag integration | Breaking change for apps using SessionGuard + Starlette SessionMiddleware |
| C: Support both via a flag | No-one is broken | Complexity doubles; two code paths to maintain forever |

## Decision

**Option B** — `SessionGuard` reads and writes `request.state.session` (`SessionData`).

Arvel is pre-1.0 (no stability guarantees per Constitution Article VI §2). The dual-session coexistence is a footgun: an app that enables both `SessionMiddleware` and `StartSession` gets silently inconsistent session state. The correct fix is a single owner. `SessionData` is strictly richer than Starlette's dict (typed flash bag, session ID regeneration, consistent storage backend).

**Migration**: Apps using `SessionGuard` with Starlette's `SessionMiddleware` must switch to `StartSession` middleware and `SessionConfig`. The change is documented in CHANGELOG and the auth guide.

**Backward compat re-exports**: `from arvel.http.auth import SessionGuard` continues to work (re-exports from `arvel.auth.guards.session_`). Only the session source changes.

## Consequences

- **Gain**: Single typed session stack; `SessionGuard.login()` can regenerate session ID safely; flash bag integration possible
- **Accept**: Breaking change for any app using `SessionGuard` + Starlette `SessionMiddleware` (pre-1.0, acceptable)
- **Risk**: Migration friction — mitigated by clear CHANGELOG entry and auth guide
