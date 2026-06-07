# Changelog

Arvel is a monorepo. Each published package keeps its own changelog, generated
from [Conventional Commits](https://www.conventionalcommits.org) by
[release-please](https://github.com/googleapis/release-please) — the version,
the date, and the commit links are all derived from history, not edited by hand.

This root file is the entry point: the cross-cutting roadmap lives in
`[Unreleased]` below, and the per-package history lives in each package's own
`CHANGELOG.md`.

## Per-package changelogs

| Package | Changelog |
|---|---|
| `arvel` (core) | [`packages/arvel/CHANGELOG.md`](packages/arvel/CHANGELOG.md) |
| `arvel-permission` | [`packages/arvel-permission/CHANGELOG.md`](packages/arvel-permission/CHANGELOG.md) |
| `arvel-image` | [`packages/arvel-image/CHANGELOG.md`](packages/arvel-image/CHANGELOG.md) |
| `arvel-oauth` | [`packages/arvel-oauth/CHANGELOG.md`](packages/arvel-oauth/CHANGELOG.md) |
| `arvel-search` | [`packages/arvel-search/CHANGELOG.md`](packages/arvel-search/CHANGELOG.md) |
| `arvel-audit` | [`packages/arvel-audit/CHANGELOG.md`](packages/arvel-audit/CHANGELOG.md) |

Packages version independently. A release tags a commit as
`<package>-v<version>` (e.g. `arvel-v0.7.2`) and publishes the matching
distribution to PyPI.

## [Unreleased]

Work in flight toward the `1.0` public-API review. Tracked here until it lands
in a tagged release; individual changes appear in the relevant package
changelog once shipped.

**Now landed and stable** (moved out of "in flight"):

- Route model binding — `routing.py:258–411, 620–751` + `test_wi055_*`
- Resource controllers (`Route.resource`, `Route.api_resource`) — `routing.py:1085–1126` + `test_wi058_*`
- Recursive tree relations (adjacency-list CTEs via `has_many_recursive`,
  `with_tree`, `Descendants`, `Ancestors`) — `database/orm/relations.py:152–266`
- Queue chain semantics — `Bus.chain` truly stops on failure; chained tail rides
  on the head envelope; sync driver runs chains inline
- Worker restart wiring — `QueueWorkCommand` now passes a live `QueueRestartSignal`
  so `queue:restart` actually halts running workers
- Scheduler `inMaintenanceMode()` and `outputTo()` honored — tasks are skipped
  when the app is down (unless opted in), and stdout/stderr can be teed to a
  file per task
- Maintenance `--render` template — `arvel down --render path/to/page.html` now
  serves that page as HTML, falling back to plain text on read errors
- Array session store — `SESSION_DRIVER=array` is registered, useful for tests
- Auth provider name — `arvent` is the canonical (and only) driver; config
  validation rejects unknown drivers at load time with a clear error
- Auth dead-field cleanup — removed inert `LoginRequest.remember` field and
  `users.remember_token` column (proper remember-me will ship as a designed
  feature, not an inert placeholder)
- `RefreshDatabase` test mixin — `from arvel.testing import RefreshDatabase`
  wraps each test in a transaction and rolls it back at teardown
- `Bus.fake()` — records every dispatched job (including chains) without
  executing handlers; ships `assert_dispatched`, `assert_not_dispatched`,
  `assert_dispatched_on`, `assert_chained`
- `Notification.fake()` — records every `Notification.send` / `send_now` call
  without invoking any channel; ships `assert_sent_to`, `assert_not_sent_to`,
  `assert_nothing_sent`
- Test-case cleanup — removed the inert `ArvelTestCase.refresh_database()`
  no-op shim; use the new `RefreshDatabase` mixin instead
- JSON HTTP helpers — `ArvelTestCase.get_json/post_json/put_json/patch_json/
  delete_json` set the right `Accept`/`Content-Type` headers and return a
  `TestResponse` directly
- Richer JSON assertions on `TestResponse` — `assert_exact_json`,
  `assert_json_fragment`, `assert_json_missing`, `assert_json_structure`
  (with `{"*": [...]}` list wildcard), `assert_json_count`,
  `assert_json_validation_errors` (handles both FastAPI `detail` and Laravel
  `errors` shapes)
- Laravel-parity validation rules — 32 new rules in the `rules()` layer:
  presence/emptiness (`nullable`, `present`, `filled`, `prohibited`), types
  (`string`, `integer`, `numeric`, `boolean`, `accepted`), formats (`email`,
  `url`, `uuid`, `ip`, `ipv4`, `ipv6`, `json`), strings (`alpha`, `alpha_num`,
  `alpha_dash`, `regex`, `not_regex`, `starts_with`, `ends_with`, `in`,
  `not_in`), size/range (`min`, `max`, `between`, `size`), comparisons
  (`confirmed`, `same`, `different`)

**Remaining priority gaps** (ordered by impact, see
[`docs/backlog/ROADMAP.md`](docs/backlog/ROADMAP.md)):

- Outbound HTTP — first-party `Http::` facade + `Http::fake` (currently apps
  call `httpx` directly)
- Needs-based CLI bootstrap — original ask: each command should boot only its
  required service providers, plus `openapi:export --output FILE` for clean
  banner separation
- Laravel-style validation rules — ~25 missing string rules (`string`,
  `integer`, `min`, `max`, `in`, `email`, `url`, `date`, `confirmed`,
  `same`, `different`, `nullable`, `bail`, …), conditional rules,
  nested/wildcard, custom rule registration, `Rule::in()` / `Rule::unique()`
  builders
- HTTP facades — `response()`, `redirect()`, `Http::` outbound client
- Route caching — `route:cache` / `route:clear`
- Needs-based CLI bootstrap (only init the providers the command needs)
  ([WI-001](docs/backlog/001-epic-needs-based-cli-bootstrap.md))
- HTTP security hardening — dedup `CsrfMismatchException`, align CSRF
  header casing, trusted-proxy middleware
- Framework-level local file serving (`STORAGE_LOCAL_SERVE`, Laravel
  `serve => true` parity)

> The headline goal before `1.0` is a public-API review and stability pass.
