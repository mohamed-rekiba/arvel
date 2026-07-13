<!-- Title must follow Conventional Commits, e.g. `feat: add rate-limiter middleware` -->

## What & why
<!-- What does this change and why does it matter? Link the issue/spec. -->

## How to test
<!-- Exact steps / commands a reviewer runs to verify. -->

## Checklist
- [ ] Conventional Commit title (drives release-please + CHANGELOG)
- [ ] `make check` green locally (lint · format · types · imports · security · coverage ≥ 95%)
- [ ] Tests added/updated (incl. abuse/negative cases where security-relevant)
- [ ] Docs updated if behavior/public API changed
- [ ] No secrets; no new high/critical `pip-audit` findings (or documented in SECURITY.md)
