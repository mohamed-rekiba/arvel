# Threat Model

STRIDE analysis for the Arvel framework core. Covers the HTTP layer, WebSocket
broadcasting, ORM/query pipeline, authentication, storage, and the scaffold CLI.

## STRIDE Table

| ID | Category | Component | Threat | Mitigation | Status |
|----|----------|-----------|--------|------------|--------|
| T-01 | Spoofing | HTTP Auth | Attacker presents a forged or expired JWT | Signature + `exp`/`iss`/`aud` validation on every request | Mitigated |
| T-02 | Spoofing | Broadcasting | Client subscribes to another user's private channel | Channel auth endpoint verifies caller identity before issuing channel token | Mitigated |
| T-03 | Tampering | Query Builder | SQL injection via user-supplied filter values | All user values pass through SQLAlchemy bound parameters; `select_raw` accepts only literal constants | Mitigated |
| T-04 | Tampering | Storage | Path traversal via crafted upload filename | Storage keys are UUID-based; client filename is ignored | Mitigated |
| T-05 | Tampering | Config Cache | Attacker replaces serialized config cache on disk | Cache file written with restricted permissions; re-generated deterministically on `optimize` | Accepted (local deploy) |
| T-06 | Repudiation | HTTP Auth | User denies performing an action | Structured audit log records `user_id`, `ip`, `action`, and timestamp | Mitigated |
| T-07 | Repudiation | Broadcasting | Client denies receiving a broadcast | Delivery receipts not guaranteed by design; at-most-once semantics documented | Accepted (design) |
| T-08 | Information Disclosure | Error Handling | Stack traces or SQL exposed in error responses | Production error handler returns generic `INTERNAL_ERROR` code; details logged server-side only | Mitigated |
| T-09 | Information Disclosure | Storage | Presigned URLs leaked or replayed | TTL enforced on presigned URLs (default 15 min); HTTPS required | Mitigated |
| T-10 | Denial of Service | HTTP | Unauthenticated flood of expensive queries | Rate limiting at gateway; DB connection pool bounded | Mitigated |
| T-11 | Denial of Service | Broadcasting | WebSocket connection exhaustion | Connection limit enforced per Reverb worker; idle connections reaped | Mitigated |
| T-12 | Elevation of Privilege | RBAC | User escalates to admin role via direct attribute assignment | Role changes require explicit grant by an existing admin; role column never set from request body | Mitigated |
| T-13 | Elevation of Privilege | ORM | Tenant isolation bypass via ORM scope removal | Global scopes enforce tenant filter; `withoutGlobalScopes()` requires explicit developer call | Mitigated |

## Spoofing Mitigations

JWT validation enforces signature algorithm (`RS256`), `exp`, `iss`, and `aud` claims.
Channel authorization re-validates the JWT before issuing short-lived channel tokens.

## Tampering Mitigations

SQLAlchemy bound parameters prevent SQL injection in all query builder paths.
UUID-keyed storage paths eliminate path traversal. Config cache permissions prevent
unauthorized replacement.

## Repudiation Mitigations

Structured logs record all authentication events, permission checks, and mutating
operations with the caller's identity and IP.

## Information Disclosure Mitigations

Production error responses expose only a machine-readable code and a human-readable
message. Internal details (stack traces, SQL, file paths) are logged server-side only.

## Denial of Service Mitigations

Rate limiting at the gateway, bounded DB connection pools, and WebSocket connection
limits prevent individual clients from exhausting shared resources.

## Elevation of Privilege Mitigations

RBAC enforces least-privilege by default (new users receive the `viewer` role). Role
escalation requires an explicit admin grant. ORM global scopes enforce tenant isolation.

## Assumptions and Out-of-Scope

- Network-layer DDoS mitigation is handled by the hosting infrastructure, not Arvel.
- Secret management (API keys, DB credentials) is the operator's responsibility.
- Physical security of the deployment host is out of scope.

## Next Review

Revisit when adding OAuth2 authorization-code flow, multi-tenant data isolation, or
payment processing.
