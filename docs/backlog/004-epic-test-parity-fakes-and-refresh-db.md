# Epic: Test parity — Laravel-style fakes & DB refresh

## Summary

Fill the gaps between Arvel's testing surface and Laravel's, so package authors and apps can write end-to-end tests without rolling their own fakes. Six concrete pieces: `Queue::fake`, `Http::fake`, `Mail::fake` (real, not just `MailManager.fake()` context), a `DatabaseTransactions` mixin sibling for `RefreshDatabase`, `without_middleware()` / `with_middleware()` test helpers, and a richer `acting_as()` that supports abilities/scopes.

Already on disk (audit confirmed): `RefreshDatabase`, `Bus::fake`, `Notification::fake`, `Event::fake`, `Cache::fake`, `Storage::fake`, `BroadcastFake`, `assert_exact_json` + the JSON helper suite (`get_json` / `post_json` / `put_json` / `patch_json` / `delete_json`).

## Stories

### Story 1: `Queue::fake` for queue-level interception

**As a** package author writing a feature that dispatches jobs,
**I want** a `Queue::fake()` context manager that records dispatched jobs without enqueueing them to a real driver,
**so that** I can assert what jobs were dispatched, on which queue, with which payload, without standing up Redis or polluting the database queue.

**Acceptance Criteria**:
- [ ] Given an app with the queue subsystem booted, when test code wraps a block in `Queue.fake()`, then any `Job.dispatch(...)` / `dispatch_now(...)` call records the job and does NOT push it to the configured driver.
- [ ] Given `Queue.fake()` is active, when the test asserts `Queue.assert_pushed(MyJob, lambda j: j.payload.user_id == 5)`, then the assertion passes when at least one recorded job matches.
- [ ] Given `Queue.fake()` is active, when the test asserts `Queue.assert_pushed_on("emails", MyJob)`, then the assertion is scoped to the named queue.
- [ ] Given `Queue.fake()` is active, when the test asserts `Queue.assert_not_pushed(MyJob)`, then the assertion passes only when no matching job was recorded.
- [ ] Given the fake is exited (context manager close), then the real queue manager is restored — subsequent dispatches go through the real driver again.
- [ ] Given a test asserts a fake method outside of `Queue.fake()`, then a clear `AssertionError` is raised (mirrors the existing `Bus.assert_*` behaviour).
- [ ] Given two test files both use `Queue.fake()` in parallel, when pytest runs them concurrently, then their recorded jobs do not bleed into each other.

**Security Requirements**:
- [ ] Fake state is fully process-local — no shared in-memory queue across worker processes that could be confused with production state.

**Documentation Requirements**:
- [ ] New section in `docs/site/docs/features/testing.md` covering `Queue::fake` with code samples.
- [ ] Cross-link from `docs/site/docs/features/queues.md` to the testing page.

**Requirement Refs**: (audit row "Test surface: Queue::fake")
**Priority**: Must
**Complexity**: Medium
**Status**: Ready

---

### Story 2: `Http::fake` for outbound HTTP mocking

**As a** package author whose code calls external APIs via `httpx`,
**I want** an `Http::fake({"github.com/*": Http.response(200, {...})})` helper,
**so that** I can write tests that never touch the network and assert what outbound calls were made.

**Acceptance Criteria**:
- [ ] Given a test wraps a block in `Http.fake({"https://api.example.com/*": Http.response(json={"ok": True})})`, when application code issues `httpx.AsyncClient().get("https://api.example.com/users")`, then the request is intercepted and the canned response is returned.
- [ ] Given `Http.fake()` is active with no mapping, when application code makes any outbound request, then a clear `AssertionError` ("unmocked HTTP request to …") is raised (strict-by-default).
- [ ] Given `Http.fake()` is active, when the test asserts `Http.assert_sent(lambda req: req.url.host == "api.example.com")`, then the assertion passes if at least one recorded request matches.
- [ ] Given `Http.fake()` is active, when the test asserts `Http.assert_not_sent(...)`, then the assertion passes only when no matching request was recorded.
- [ ] Given `Http.fake()` exits, then the real httpx transport is restored.
- [ ] Given the framework binds a shared `httpx.AsyncClient` in the container, when `Http.fake()` is active, that client uses the mock transport — no extra wiring required in user code.

**Security Requirements**:
- [ ] When `Http.fake()` is active, no outbound socket may be opened — verify with a unit test that registers a forbidden host.

**Documentation Requirements**:
- [ ] New section in `docs/site/docs/features/testing.md` covering `Http::fake` with code samples and the strict-by-default behaviour.

**Requirement Refs**: (audit row "Test surface: Http::fake")
**Priority**: Must
**Complexity**: Medium
**Status**: Ready

---

### Story 3: `Mail::fake` as a first-class test fake

**As a** package author whose code sends mail via the `Mail` facade,
**I want** `Mail::fake()` to behave like the other faces (`Bus`, `Notification`, `Event`) with `assert_sent`, `assert_not_sent`, `assert_sent_count` helpers,
**so that** I don't have to drop down to inspecting the `array` driver's outbox manually.

**Acceptance Criteria**:
- [ ] Given a test wraps a block in `Mail.fake()`, when application code calls `Mail.to(user).send(WelcomeMail(...))`, then the message is recorded and not sent.
- [ ] Given `Mail.fake()` is active, when the test asserts `Mail.assert_sent(WelcomeMail, lambda m: m.has_to("a@b.c"))`, then it passes when a matching message was recorded.
- [ ] Given `Mail.fake()` is active, when the test asserts `Mail.assert_not_sent(PasswordResetMail)`, then it passes when no such message was recorded.
- [ ] Given `Mail.fake()` is active, when the test asserts `Mail.assert_sent_count(2, WelcomeMail)`, then it passes when exactly two matching messages were recorded.
- [ ] Given `Mail.fake()` exits, then the real mail manager is restored.
- [ ] Given `Mail.fake()` is nested inside another fake context, then both fakes record independently (no leaking).

**Security Requirements**:
- [ ] Fake state must not bleed across test processes.

**Documentation Requirements**:
- [ ] Update `docs/site/docs/features/mail.md` testing section.

**Requirement Refs**: (audit row "Test surface: Mail::fake")
**Priority**: Must
**Complexity**: Small
**Status**: Ready

---

### Story 4: `DatabaseTransactions` mixin

**As a** test author whose test suite already has a clean schema from a global `RefreshDatabase` setup,
**I want** a lighter `DatabaseTransactions` mixin that wraps each test in a savepoint and rolls back at teardown,
**so that** my fast-path tests don't pay the cost of dropping/migrating between every test.

**Acceptance Criteria**:
- [ ] Given a `DatabaseTransactions` test runs, when the test creates DB rows, then the rows are rolled back on teardown and never visible to the next test.
- [ ] Given the test suite mixes `RefreshDatabase` and `DatabaseTransactions` cases, when both run in the same session, then neither bleeds state into the other.
- [ ] Given a `DatabaseTransactions` test raises mid-test, when teardown runs, then the savepoint is still rolled back (no dangling transaction).
- [ ] Given the app has no DB engine bound, when a `DatabaseTransactions` test runs, then the mixin is a no-op (mirrors `RefreshDatabase` behaviour today).
- [ ] Given the test calls `await db_commit()` to materialise data for an assertion mid-test, when the test ends, the data still rolls back (savepoint-on-savepoint).

**Security Requirements**: none.

**Documentation Requirements**:
- [ ] Update `docs/site/docs/features/testing.md` to position `DatabaseTransactions` next to `RefreshDatabase` — when to use each.

**Requirement Refs**: (audit row "Test surface: DatabaseTransactions")
**Priority**: Should
**Complexity**: Small
**Status**: Ready

---

### Story 5: Middleware bypass test helpers

**As a** test author writing controller tests,
**I want** `self.without_middleware()` and `self.with_middleware(SomeMiddleware)` helpers on `ArvelTestCase`,
**so that** I can isolate a controller's behaviour from auth/CSRF/throttle middleware without rewriting the test app.

**Acceptance Criteria**:
- [ ] Given a test calls `self.without_middleware()`, when subsequent requests pass through the router, then registered middleware (auth, CSRF, throttle) does not run for those requests.
- [ ] Given a test calls `self.without_middleware(CsrfDoubleSubmitMiddleware)`, when subsequent requests pass through the router, then only the CSRF middleware is skipped — other middleware still runs.
- [ ] Given a test calls `self.with_middleware(MyExtraMiddleware)`, when subsequent requests pass through the router, then the additional middleware runs in addition to the registered ones.
- [ ] Given the helper's context ends (teardown), then the middleware configuration is restored — the next test sees the original stack.

**Security Requirements**:
- [ ] `without_middleware` MUST raise if called outside `env=testing` (mirrors `acting_as`).

**Documentation Requirements**:
- [ ] Add a "middleware bypass" subsection to `docs/site/docs/features/testing.md`.

**Requirement Refs**: (Laravel parity polish, not in original audit row but blocks WI-006 testing)
**Priority**: Should
**Complexity**: Small
**Status**: Ready

---

### Story 6: Richer `acting_as` with abilities

**As a** test author writing tests for a token-guarded endpoint,
**I want** `self.acting_as(user, abilities=["posts:write"])` to attach the abilities to the test request,
**so that** I can assert Sanctum/JWT scope behaviour without minting real tokens.

**Acceptance Criteria**:
- [ ] Given `self.acting_as(user, abilities=["posts:write"])`, when the next request authenticates, then the user's abilities are exposed on `request.user.abilities` (or the guard-specific equivalent).
- [ ] Given `self.acting_as(user, guard="api")`, when the next request authenticates, then the API guard is used (not the default `web` guard).
- [ ] Given two calls to `acting_as` in a row, when the second call runs, then it replaces the first (last write wins).
- [ ] Given `self.acting_as_guest()` (new helper), when the next request authenticates, then no user is attached — endpoints that require auth return 401.

**Security Requirements**:
- [ ] The helper MUST refuse to run outside `env=testing` (already true; just preserve).

**Documentation Requirements**:
- [ ] Update the `acting_as` section in `docs/site/docs/features/testing.md`.

**Requirement Refs**: (related to audit row "Auth UX: User::can()" but lives on the test surface)
**Priority**: Could
**Complexity**: Small
**Status**: Ready

---

## Dependencies

- WI-002 (Queue & Scheduler honesty) and WI-003 (Auth & Maintenance dead-fields) should land first — Story 1 (`Queue::fake`) depends on the queue subsystem behaving honestly after WI-002.
- No dependency on WI-001 (CLI bootstrap) — testing utilities don't touch the CLI path.

## Notes

- Use `httpx.MockTransport` as the foundation for Story 2 (`Http::fake`) — same pattern as `httpx.ASGITransport` already used by `ArvelTestCase.client`.
- For Story 1 (`Queue::fake`), follow the exact shape of the existing `Bus::fake` in `packages/arvel/src/arvel/facades/bus.py` — same `_FakeContext` pattern, same `assert_pushed` / `assert_not_pushed` naming.
- For Story 4 (`DatabaseTransactions`), wrap each test in `await connection.begin_nested()` rather than `await engine.connect() + connection.begin()`, so it composes inside a transaction that an outer `RefreshDatabase` may have already opened at suite level.
- Story 5 (`without_middleware`) is the cleanest blocker for WI-006 testing — without it, the route-cache test cases will have to fight CSRF setup. Keep it in this epic rather than deferring.
