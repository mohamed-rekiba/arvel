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
- Auth provider name — `database` is the canonical (and only) driver string;
  `ProviderConfig.driver` rejects unknown values at config load time with a
  clear `"Valid drivers: 'database'."` error. The implementation class
  (`ArventUserProvider`, in `arvel.auth.providers.arvent`) is wired to that
  string — the class name reflects the underlying Arvent ORM, the driver
  string stays generic to match the kit + stub scaffolding.
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
- Laravel-parity validation rules — 32 rules in the `rules()` layer:
  presence/emptiness (`nullable`, `present`, `filled`, `prohibited`), types
  (`string`, `integer`, `numeric`, `boolean`, `accepted`), formats (`email`,
  `url`, `uuid`, `ip`, `ipv4`, `ipv6`, `json`), strings (`alpha`, `alpha_num`,
  `alpha_dash`, `regex`, `not_regex`, `starts_with`, `ends_with`, `in`,
  `not_in`), size/range (`min`, `max`, `between`, `size`), comparisons
  (`confirmed`, `same`, `different`)
- Validation parity round 2 — `bail` (stop a field at the first failure),
  conditional presence (`required_if`, `required_unless`, `required_with`,
  `required_with_all`, `required_without`, `required_without_all`), dates
  (`date`, `date_format`, `before`, `after`, `before_or_equal`,
  `after_or_equal`), `register_rule()` for custom rules, and `Rule` builders
  (`in_`, `not_in`, `exists`, `unique`, `required_if`, `required_unless`) —
  `validation/rules.py`, `validation/rule.py`, `validation/validator.py` +
  `test_wi044_*`
- Nested/wildcard validation — dot-notation (`address.city`) and `*` wildcards
  (`items.*.id`, dict wildcards, explicit indices); failures key by concrete
  path; wildcards iterate only existing entries while non-wildcard nested paths
  always validate; messages key by wildcard or concrete path. Completes the
  validation parity backlog. `validation/validator.py` (`resolve_targets`) +
  `test_wi045_*`
- Response/redirect helpers — `response().json/text/make/no_content`,
  `redirect(to)`, `to_route(name, **params)`, `back(request)`, and
  `redirect(...).with_(request, key=value)` to flash into the session before
  redirecting. `http/responses.py` + `test_wi046_*`
- Outbound HTTP — first-party `Http` facade over `httpx` with a fluent
  `PendingRequest` builder (`with_headers/with_token/with_basic_auth/accept_json/
  as_form/timeout/base_url`), verb methods (`get/head/post/put/patch/delete`),
  and a predicate-rich `Response` (`ok/successful/redirect/failed/client_error/
  server_error/json/body/header`). `Http.fake({pattern: Http.response(...)})`
  records and stubs requests (glob match, empty-200 default so tests never hit
  the network) with `recorded()`, `assert_sent`, `assert_not_sent`,
  `assert_sent_count`, `assert_nothing_sent`. `http/client.py`,
  `facades/http.py`, `testing/fakes/http.py` + `test_wi047_*`
- Framework-level local file serving — `STORAGE_LOCAL_SERVE` registers a route at
  `STORAGE_LOCAL_URL` that serves files from the local disk (Laravel `serve =>
  true` parity), with path-traversal protection and signed/temporary-URL support.
  Skipped when the disk URL is absolute (CDN) or serve is off.
  `providers/storage_provider.py` + `test_serve_route`
- Needs-based CLI bootstrap — each command declares its `requires` subsystems
  (`CliSubsystem`) and only those service providers boot; non-HTTP commands skip
  route loading and the registered-routes banner
- `openapi:export --output FILE` — exports the spec to a file (or `-`/`--stdout`),
  YAML or JSON, with status text on stderr so stdout stays clean
- CSRF consolidation — the session (`VerifyCsrf`) and cookie
  (`CsrfDoubleSubmitMiddleware`) checks now share a single
  `CsrfMismatchException` (419, `CSRF_MISMATCH`); the cookie check moved off its
  old 403. Both accept the `X-XSRF-TOKEN` header alongside `X-CSRF-TOKEN`, and
  `VerifyCsrf` also reads the `_token` field of urlencoded form posts (Laravel's
  token-source order). `http/exceptions.py`, `http/_middleware_core.py`,
  `auth/middleware/csrf_double_submit.py` + `test_csrf*`
- TrustProxies request middleware — `TrustProxiesMiddleware` honors
  `X-Forwarded-For/-Proto/-Host` only when the TCP peer is a configured trusted
  proxy, so behind a load balancer `request.client.host` (and the throttle key
  that reads it), the scheme, and the host all reflect the real client.
  Configured via `TRUSTED_PROXIES` (CSV of IPs/CIDRs, or `*` to trust all);
  mounted as the outermost layer only when set. `http/config.py`,
  `http/middleware/trust_proxies.py` + `test_trust_proxies`

All bucket-3 feature-parity gaps triaged on 2026-06-09 (see
`.context/research/043-feature-gap-bucket3-triage.md` and
[`docs/backlog/043-epic-feature-gap-bucket3-triage.md`](docs/backlog/043-epic-feature-gap-bucket3-triage.md))
are now closed.

**Deliberately not implemented:**

- Route / event caching (`route:cache`, `event:cache`) — not applicable on
  Python. Laravel can serialize string actions (`Controller@method`); Arvel
  routes and listeners are live callables that can't be safely serialized, and
  importing them is already `.pyc`-cached, so a cache buys nothing. `optimize`
  now reports these as n/a. See `.context/research/048-route-cache-decision.md`.

> The headline goal before `1.0` is a public-API review and stability pass.
