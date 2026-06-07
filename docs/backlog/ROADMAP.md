# Backlog roadmap

Master plan for product backlog epics. Each entry links to a numbered epic file with the story breakdown.

## Active

| # | Epic | Priority | Complexity | Status | File |
|---|---|---|---|---|---|
| 002 | Queue & Scheduler honesty fixes | Must | L2 | Ready | [`002-epic-queue-scheduler-honesty.md`](./002-epic-queue-scheduler-honesty.md) |
| 003 | Auth & Maintenance dead-field cleanup | Must | L2 | Ready | [`003-epic-auth-maintenance-dead-fields.md`](./003-epic-auth-maintenance-dead-fields.md) |
| 004 | Test parity — Laravel-style fakes & DB refresh | Must | L3 | Ready | [`004-epic-test-parity-fakes-and-refresh-db.md`](./004-epic-test-parity-fakes-and-refresh-db.md) |
| 007 | Doc & CHANGELOG freshness pass | Must | L1 | Ready | [`007-epic-changelog-and-docs-freshness.md`](./007-epic-changelog-and-docs-freshness.md) |

## Shipped

| # | Epic | Landed | File |
|---|---|---|---|
| 001 | Needs-based CLI bootstrap | 2026-06-05 | [`001-epic-needs-based-cli-bootstrap.md`](./001-epic-needs-based-cli-bootstrap.md) |

## Suggested execution order (2026-06-05 review, updated 2026-06-05)

Source: parallel parity audit (validation / routing / ORM / messaging / auth) — see
[`docs/plans/2026-06-05-laravel-parity-review.md`](../plans/2026-06-05-laravel-parity-review.md).

1. ~~**WI-001** — needs-based CLI bootstrap.~~ **Shipped 2026-06-05.**
2. **WI-002** — surgical bug fixes; small blast radius, immediate user-trust win.
3. **WI-003** — same shape, immediate honesty win in auth/maintenance.
4. **WI-007** — cleanup pass riding on top of the WI-002 / WI-003 changelog updates.
5. **WI-004** — test parity (`RefreshDatabase`, `Queue::fake`, etc.) — unblocks faster iteration on later WIs.
6. **WI-005** (planned) — validation rule expansion (~25 missing rules).
7. **WI-006** (planned) — HTTP facades + route caching.
8. **WI-008** (planned) — HTTP security hardening (CSRF dedup, trusted proxies, header case).

WIs 005, 006, 008 will be filed as epics in the next iteration once 002/003/004/007 land.

## Notes

- New epics are added at the next free three-digit prefix and linked here.
- Move epics out of "Active" into a "Done" or "Shipped" section once their work items close.
