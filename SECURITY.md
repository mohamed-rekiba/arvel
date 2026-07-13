# Security Policy

arvel is a web framework: its defaults are the security posture of every app built on
it. We treat secure-by-default as a correctness property and gate every commit on it.

## Supported versions

arvel is pre-1.0 (`0.x`). Security fixes land on `main` and the latest released `0.x`.
Pin a version and watch releases until 1.0.

## Reporting a vulnerability

**Do not open a public issue for a security report.** Email the maintainer privately
(or use GitHub's *Report a vulnerability* / private security advisory on the repo).
Include: affected version, a minimal reproduction, and impact. We aim to acknowledge
within 72 hours and to ship or document a fix or mitigation before public disclosure.

## How we test for security

Security is a standing CI gate, not a one-off:

- **SAST** — `bandit` runs on every push/PR (blocking).
- **SCA** — `pip-audit` runs on every push/PR (**blocking**); new high/critical CVEs in
  dependencies fail the build. See the carve-out below.
- **Abuse/negative tests** — the suite asserts the framework *refuses* unintended input
  (injection, traversal, auth bypass, tampered/expired signatures, oversized/malformed
  payloads), not just happy paths. Input-boundary code is exercised with generated
  (property-based) inputs, not only hand-picked examples.

Run locally: `make security` (bandit), `make audit` (pip-audit), `make test`,
`make check` (all gates).

## Known accepted risks

| ID | Package | Status | Rationale |
|----|---------|--------|-----------|
| GHSA-qhqw-rrw9-25rm / CVE-2025-65896 | `asyncmy` (optional `mysql` extra) | Accepted-risk, carved out of the SCA gate | SQL injection via crafted dict keys. **No upstream fix exists** (0.2.11 is latest; all versions affected). `asyncmy` is the DBAPI driver under SQLAlchemy and is **not reachable through arvel's ORM/query-builder** — bind-parameter names are compiler-generated, never user input. Only an app dropping to raw `asyncmy` with user-controlled dict keys is exposed. Revisit when upstream ships a fix or if `aiomysql` becomes the default MySQL driver. |

This is the **only** suppressed finding; any other vulnerability fails the gate.

## Secure-by-default expectations for apps

- CSRF protection, signed-URL verification, encrypted cookies, and password hashing are
  on by default — don't disable them without a documented reason.
- Pass untrusted data as **bound parameters**, never string-formatted into SQL; the
  query builder does this for you.
- Keep secrets in environment/config, never in code or commits.
