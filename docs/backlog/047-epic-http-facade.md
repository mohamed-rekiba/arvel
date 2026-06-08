# Epic: Http facade + Http.fake (outbound HTTP client)

## Summary
First-party outbound HTTP over `httpx2` — a Laravel-style `Http` facade plus a
recording/stubbing test fake (WI-043 bucket-3 gap, high impact). Additive; apps
can still use `httpx` directly.

**Spec:** `docs/pipeline/specs/WI-arvel-047-http-facade.md`

## Delivered

### Story 1: Fluent request builder — Done
`PendingRequest` with `with_headers/with_token/with_basic_auth/accept/
accept_json/as_form/timeout/base_url` and async verbs
`get/head/post/put/patch/delete`. JSON bodies by default; `base_url` joins
relative paths and ignores absolute ones.

### Story 2: Response wrapper — Done
`Response` predicates (`ok/successful/redirect/failed/client_error/server_error`)
plus `json/body/header/headers/raise_for_status/status/raw`.

### Story 3: Http.fake — Done
`Http.fake({pattern: Http.response(...)})` records and stubs requests
(scheme-insensitive glob match, empty-200 default so tests never hit the
network). Assertions: `recorded/assert_sent/assert_not_sent/assert_sent_count/
assert_nothing_sent`. `ContextVar`-scoped so the client has no runtime
dependency on the testing package.

## Tests
`packages/arvel/tests/http/test_wi047_http_facade.py` — 18 cases.

## Gates
ruff clean; mypy 0 (1073 files); pyright 0/0; http suite 227 passed; mkdocs
--strict clean.
