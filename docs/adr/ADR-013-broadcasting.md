# ADR-013 — Broadcasting (Reverb)

**Status**: Accepted
**Date**: original decisions 2026-05-18 – 2026-05-19; merged into one ADR on 2026-06-07 during the WI-arvel-005 consolidation pass
**Scope**: Broadcaster protocol layout, channel registry pattern matching, ShouldBroadcast mixin, Reverb single event loop, Pusher protocol v7 surface, channel-auth HMAC scheme, broadcaster fake in arvel.testing, bench-reverb hard-gate.

## Why this is one ADR

Broadcasting and the Reverb broker are one design: protocol shape, channel registry, broker loop, transport. The eight ADRs are joints of the same machine.

---

## § 1 — `Broadcaster` Protocol + Driver Layout

**Originally**: ADR-105 · Date: 2026-05-18

### Context

The broadcasting subsystem needs a stable driver contract. Four shipped drivers (`log`, `null`, `redis-pubsub`, `pusher`) plus user-defined drivers must all conform. Three candidates:

- **A**: Inheritance — `class Broadcaster(ABC)` with `@abstractmethod async def broadcast(...)`.
- **B**: `typing.Protocol` with `@runtime_checkable` — structural typing, no ABC.
- **C**: Concrete class with a callback registry — closures pretending to be drivers.

### Decision

**Option B** — `Broadcaster` is a `@runtime_checkable` `typing.Protocol`. Drivers live at `arvel.broadcasting.drivers.{log_,null_,redis_,pusher_}.py`. `BroadcastManager.driver(name)` is the single resolver.

Layout mirrors `arvel.cache.manager.CacheManager` / `arvel.session.manager.SessionManager` / `arvel.storage.manager.StorageManager` — established framework pattern (WI-006). Familiar, type-safe, and zero-friction for users adding their own driver.

### Consequences

- User-defined drivers do NOT need to import `arvel.broadcasting.Broadcaster` to inherit from it; structural typing matches by shape.
- `isinstance(driver, Broadcaster)` works at runtime for tests and assertions.
- The driver constructor signature is each driver's concern — `_resolve(name)` in the manager owns construction-time wiring (lazy imports for the optional `redis` and `httpx` deps).
- Driver filenames end in `_` (e.g., `log_.py`) to avoid shadowing Python's `logging` module.

---

## § 2 — `Broadcast.channel()` Registry — Exact Pattern Matching, No Wildcards

**Originally**: ADR-106 · Date: 2026-05-18

### Context

`Broadcast.channel("private-user.{id}")` registers an auth callback. Three candidates for the matching semantics:

- **A**: Full regex (`@Broadcast.channel(r"^private-user\.(?P<id>\d+)$")`) — power user friendly, security-tricky.
- **B**: Exact pattern with `{placeholder}` substitutions matching `[^./]+` — Laravel-style, predictable.
- **C**: Prefix match + parameter parsing (`"private-user.*"` → all `private-user.*` channels) — simple but ambiguous.

### Decision

**Option B** — Patterns use `{name}` placeholders. Each placeholder compiles to a `(?P<name>[^./]+)` regex group; the rest of the pattern is `re.escape`'d. Match is anchored with `fullmatch`.

Examples:
- `"private-user.{id}"` matches `"private-user.5"` (id=`"5"`) and `"private-user.alice"` (id=`"alice"`).
- `"private-user.{id}"` does NOT match `"private-user.5.admin"` (the `.admin` segment falls outside the placeholder class).
- `"presence-team.{team}.room.{room}"` matches `"presence-team.42.room.3"` (team=`"42"`, room=`"3"`).

Multiple patterns may be registered; lookup is first-match-wins in registration order.

### Consequences

- **Pro**: Whole classes of channel-name injection bugs are eliminated by construction. `"private-../admin"` cannot match `"private-user.{id}"` — `..` falls outside `[^./]+`.
- **Pro**: Matches Laravel's `Broadcast::channel("private-user.{userId}", ...)` mental model exactly.
- **Pro**: No user-supplied regex; users can't accidentally write a catastrophic-backtracking pattern.
- **Con**: No globs or wildcards. Users wanting "all private-* channels go through one callback" must register one pattern per shape. We consider this a feature, not a limitation — explicit > magic.
- Duplicate-pattern registration raises `BroadcastException` at register time (loud, not silent).

---

## § 3 — `ShouldBroadcast` is a Mixin on `Event`, Not a Separate Listener Type

**Originally**: ADR-107 · Date: 2026-05-18

### Context

Laravel marks broadcasting events by implementing the `ShouldBroadcast` interface. Three Pythonic candidates:

- **A**: Marker mixin (`class OrderShipped(Event, ShouldBroadcast):`). `EventDispatcher` checks `isinstance(event, ShouldBroadcast)`.
- **B**: Separate `BroadcastEvent` base class users inherit from instead of `Event`.
- **C**: Decorator `@broadcastable(channels=["..."])` applied to a regular `Event` subclass.

### Decision

**Option A** — `ShouldBroadcast` is a mixin (alongside the existing `Event` base) with optional override hooks `broadcast_on`, `broadcast_as`, `broadcast_with`. `EventDispatcher.dispatch` checks `isinstance(event, ShouldBroadcast)` and calls `Broadcast.send(event)` after running listeners.

Matches the existing `ShouldQueue` mixin pattern (WI-009 ADR-011 § 5), keeps the Laravel mental model 1:1, and composes cleanly with `ShouldQueue` (an event can be both queued AND broadcasted).

### Consequences

- An event mixing in `ShouldBroadcast` without overriding `broadcast_on()` raises `NotImplementedError` at dispatch time. Loud failure, not silent no-op.
- The dispatcher runs listeners FIRST, then broadcasts. Order is deterministic and matches Laravel. Broadcast failures are caught + logged; listeners always run regardless.
- Composition: an event can mix `ShouldBroadcast` AND `ShouldQueue`. The listener runs queued; the broadcast runs synchronously from the original dispatch site. This is intentional — broadcasting is typically faster than queueing a listener job, and delaying user-facing real-time messages defeats the purpose.
- Default `broadcast_with()` returns `model_dump()` for Pydantic-based events (which is all of them post-ADR-012 § 1). Users override only when they need to trim or shape the payload.

---

## § 4 — Reverb is Single-Event-Loop + Redis Pub/Sub Horizontal Scale

**Originally**: ADR-108 · Date: 2026-05-18

### Context

How to scale the Reverb WS server across CPU cores and hosts? Three candidates:

- **A**: Single asyncio event loop per process; scale horizontally by running N processes that share a Redis Pub/Sub channel.
- **B**: Multi-process within one host via `multiprocessing` + IPC for cross-process subscription state.
- **C**: Single process, multiple event loops via thread-per-loop with a coordinator.

### Decision

**Option A** — One process equals one asyncio event loop. Subscriptions are tracked per-process in memory. Cross-process fan-out is via Redis Pub/Sub (the `RedisBroadcaster` PUBLISHes; every reverb process PSUBSCRIBEs to `arvel.broadcasting.*` and forwards matching messages to its locally connected sockets).

Matches Laravel Reverb's design (Reverb runs single-threaded ReactPHP; horizontal scale is process-level). Matches `arvel queue:work` worker design (one worker per process, scale via process count). Doesn't add a new operational concept.

### Consequences

- **Pro**: Operationally simple. `systemd` units, supervisor configs, Kubernetes Deployments all work without ceremony.
- **Pro**: Zero cross-process IPC complexity. Redis is already a hard dependency for the framework's queue, cache, session paths.
- **Pro**: Each process is independent; killing one doesn't affect others. Rolling deploys with drain-then-replace work cleanly.
- **Con**: Bound by the single event loop's throughput. Per NFR-013-004, we target ≥ 1000 concurrent connections per process at < 5 % CPU each (steady-state idle). High-write-throughput channels with thousands of subscribers per channel will eventually saturate a single loop — at which point operators add more processes.
- **Con**: A subscriber on process A won't receive `except_socket_id=X` exclusions for an event broadcast on process B unless we include `socket_id` in the Redis envelope. We do. The connection that originated the broadcast knows its own `socket_id` from `pusher:connection_established` and passes it via the auth controller / HTTP context.
- Presence-channel member rosters are per-process. A user on process A is NOT visible in the roster sent to a new subscriber on process B. Documented limitation for v1; cross-process presence sync deferred to WI-016 hardening if user demand surfaces.

---

## § 5 — Pusher Protocol v7 — What We Implement, What We Don't

**Originally**: ADR-109 · Date: 2026-05-18

### Context

The Pusher Channels v7 protocol has a wide surface. Implementing it all is overkill for an MVP; cherry-picking is dangerous because `pusher-js` / `laravel-echo` expect specific frames. Need to fix a contract that satisfies the common clients without overspending.

### Decision

We implement the minimum subset required for `pusher-js` v8.5.0 and `laravel-echo` v1.x to function for public, private, and presence channels:

**Server → client frames**:
- `pusher:connection_established` (on WS open, with `{socket_id, activity_timeout}`)
- `pusher:error` (codes 4200 invalid msg, 4009 auth failed, 4301 rate limited; full Pusher 4xxx code list documented but only these three emitted)
- `pusher:pong`
- `pusher_internal:subscription_succeeded`
- `pusher_internal:member_added` / `pusher_internal:member_removed` (presence only)

**Client → server frames**:
- `pusher:ping`
- `pusher:subscribe` (with optional `auth` + `channel_data`)
- `pusher:unsubscribe`

We explicitly do NOT implement:
- `client-*` events (client-initiated direct messages).
- `pusher:signin` (user authentication binding — a v7.2 addition).
- `pusher:cache_miss`, `pusher:cache_*` (cache channels).
- The `?protocol=N` query parameter for protocol negotiation — we accept any value and reply with the v7 frames regardless.

A `tests/reverb/test_pusherjs_contract.py` runs a Node subprocess with `pusher-js@8.5.0` against an in-process `ReverbServer` to assert the contract works against the real client. If `pusher-js` changes incompatibly upstream, this test catches it.

### Consequences

- **Pro**: ~70 % of the protocol delivered with ~30 % of the spec text. Common-case clients work without modification.
- **Pro**: Contract-test pinning means breaking changes upstream surface as a failed CI check, not as a silent runtime bug.
- **Con**: Users who need `client-*` events (e.g., for typing indicators broadcast peer-to-peer without server round-trip) cannot. Documented; defer to a future WI if real demand surfaces.
- **Con**: The protocol-version query parameter is ignored — a v8 client expecting v8 semantics would get v7. Mitigated by the fact that `pusher-js` v8.5.0 sends `protocol=7` itself; upgrade-path pain is hypothetical.
- Frame parsing errors yield `pusher:error code=4200`; auth failures `code=4009`; rate-limit `code=4301`. No other error codes are emitted.

---

## § 6 — Channel-Auth HMAC-SHA256 Signature Scheme

**Originally**: ADR-110 · Date: 2026-05-18

### Context

Private and presence channels require server-side authorization. The client receives an opaque token from `POST /broadcasting/auth` and includes it in `pusher:subscribe`. The Reverb server validates the token against the receiving socket's `socket_id`. Three options for the token scheme:

- **A**: HMAC-SHA256 over `socket_id:channel_name` (private) / `socket_id:channel_name:channel_data_json` (presence). Pusher v7 server-library spec.
- **B**: JWT signed with HS256 / RS256 containing `socket_id` and `channel_name` claims. Modern but heavier and incompatible with `pusher-js`.
- **C**: Random opaque token stored in Redis with TTL, server-side lookup on subscribe. Heavier per-subscribe cost; needs cache invalidation.

### Decision

**Option A** — HMAC-SHA256 per the Pusher v7 spec.

Signature input:
- Private: `<socket_id>:<channel_name>`
- Presence: `<socket_id>:<channel_name>:<channel_data_json>`

Algorithm: HMAC-SHA256.
Output: lowercase hex digest.
Wire format: `<app_key>:<hex_digest>`.

Verification uses `hmac.compare_digest` (constant-time) against a server-recomputed signature with its own secret + this socket's `socket_id` + the requested `channel_name`.

### Consequences

- **Pro**: Exact compatibility with `pusher-js` v8.5.0 and `laravel-echo`. Zero per-client modification.
- **Pro**: Stateless — no Redis lookup, no DB hit per subscribe. Scales linearly with connections.
- **Pro**: Non-replayable across sockets. Stealing a signature from a captured network trace and replaying on a different socket fails because the `socket_id` doesn't match.
- **Con**: Signature is stateless within the validity window of the user's session. A signature obtained for `channel = private-user.5` remains valid until the socket disconnects. We treat this as acceptable: the socket itself is the lifetime; logout invalidates the session, which kills the WS via the next protocol round-trip if the client respects 401.
- **Con**: The app secret is symmetric and shared between the HTTP auth controller and every Reverb process. `BroadcastConfig.reverb.secret` is wrapped in `SecretStr`; gitleaks gate (Article V) prevents accidental commit; rotation requires restarting all reverb processes (documented).
- For presence channels, `channel_data` is included in the signed input so a man-in-the-middle cannot substitute a different presence payload while keeping a valid signature.

---

## § 7 — `BroadcasterFake` Lives Under `arvel.testing.broadcasting`

**Originally**: ADR-111 · Date: 2026-05-18

### Context

`BroadcasterFake` is a test-only `Broadcaster` implementation that records broadcasts in memory for assertion. Where does it live?

- **A**: `arvel.testing.broadcasting.BroadcasterFake` — under a new top-level `arvel.testing` package, anticipating WI-015 Quality which will ship a full `ArvelTestCase` + `Fake*` suite.
- **B**: `arvel.broadcasting.testing.BroadcasterFake` — under the subsystem it tests; easier to import in tests of just that subsystem.
- **C**: Ship it in WI-015 only; WI-013 tests use a hand-rolled stub.

### Decision

**Option A** — `arvel.testing.broadcasting.BroadcasterFake`. WI-013 establishes the `arvel.testing/` directory as a first-class part of the public API surface, with `arvel.testing.broadcasting` as its first occupant. WI-015 will add `arvel.testing.{mail,notifications,events,cache,...}` siblings.

This is consistent with Laravel's `Illuminate\Support\Testing\Fakes\BroadcastFake` namespace: testing utilities are a domain of their own, not a sub-namespace of each production subsystem. It also avoids the awkward pattern of production code optionally importing from `arvel.broadcasting.testing` (a layering smell — production shouldn't import from a `testing/` submodule even at type-check time).

### Consequences

- **Pro**: `arvel.testing` is now a first-class import path. WI-015 grows it without restructuring.
- **Pro**: Mirrors Laravel's mental model exactly.
- **Pro**: Production code under `arvel.broadcasting.*` never imports anything from `arvel.testing.*` — clean layering.
- **Con**: One extra namespace level on every import (`from arvel.testing.broadcasting import BroadcasterFake` vs `from arvel.broadcasting.testing import BroadcasterFake`). Minor.
- `BroadcasterFake.bind()` is an `async @contextmanager` that swaps the bound broadcaster on the container and restores the original on exit. Tests use it via pytest fixture or directly:
  ```python
  async with BroadcasterFake.bind() as fake:
      await Event.dispatch(MyEvent(...))
      fake.assert_broadcasted(MyEvent, on_channels=["..."])
  ```
- The fake records `RecordedBroadcast(event_name, channels, payload, except_socket_id)` immutably. `recorded()` returns a `tuple` so test assertions cannot mutate the record list.

---

## § 8 — Promote `bench-reverb` from advisory to hard CI gate

**Originally**: ADR-112 · Date: 2026-05-19

### Context

WI-014 added a `bench-reverb` CI job that runs `benchmarks/bench_reverb.py` on every push and PR. It enforces two thresholds in code (5 ms p99 publish-to-subscribe latency, 64 MiB incremental resident memory growth at 1000 connections × 100 channels) but ships with `continue-on-error: true` — so a regression *prints red* without actually blocking the PR.

ADR-013 § 8 documented this as intentional: shared GitHub Actions runners are noisy, and we lacked baseline data to set thresholds that wouldn't either (a) constantly flake (too tight) or (b) be useless (too loose).

The deferred-FB document `docs/backlog/017-deferred-from-realtime-hardening.md` slotted this for WI-017 (Hardening), with the explicit action: collect baseline data, compute a 1.5× p99 envelope, then promote the gate.

---

### Decision

Promote `bench-reverb` to a **hard** CI gate at thresholds calibrated to **1.5× the observed local-replay p99**.

Concretely:

1. The existing code-internal NFR thresholds in `bench_reverb.py` (5 ms p99 latency, 64 MiB memory) **stay as the PRD/NFR contract**.
2. The CI gate uses **looser** thresholds derived from a 50-run local-replay calibration (S2.4 script `benchmarks/scripts/calibrate_bench_reverb.py`). The looser CI gate exists to absorb GitHub runner noise without letting any real regression slip past the contract envelope.
3. The `continue-on-error: true` flag is removed from the `bench-reverb` job.
4. A new `bench-tracemalloc` job runs the byte-granular memory measurement (FB-014-002) with its own (initially looser) gate.

---

### Calibration (to be populated during S2 execution)

Run `python benchmarks/scripts/calibrate_bench_reverb.py --runs 50` locally on a quiet machine and record the output here. The script reports:

| Metric | Median | p99 | p99 × 1.5 (proposed CI gate) | Code-internal NFR |
|---|---|---|---|---|
| `publish_to_subscribe_p99_ms` | TBD | TBD | TBD | 5.0 ms |
| `incremental_resident_memory_mib` | TBD | TBD | TBD | 64 MiB |
| `tracemalloc_heap_delta_mib` | TBD | TBD | TBD | (new) |

After calibration, the chosen gate values are committed to:

- `benchmarks/bench_reverb.py` — code-internal NFR thresholds (unchanged at 5 ms / 64 MiB).
- `.github/workflows/ci.yml` — CI gate thresholds (= 1.5× observed p99).
- This ADR — record of the calibration outcome.

---

### Consequences

**Pros**:
- A real broadcasting perf regression now blocks the PR.
- The CI gate is empirically derived, not a guess.
- The calibration script is re-runnable; when we change the bench or migrate runners, we re-calibrate, not re-guess.

**Cons**:
- Shared-runner noise may still cause occasional flakes. Mitigation: the calibration script is re-runnable in <5 min; if flakes become a problem, we re-calibrate (or, as ADR-013 § 8 anticipated, migrate to a self-hosted quiet runner).
- The CI gate threshold and the code-internal NFR threshold are now two separate numbers. The discipline is: NFR is the **product contract**, CI gate is the **measurement contract**. They are documented as different things on purpose.

---

### Alternatives considered

1. **Keep advisory** — rejected. We can't claim 1.0.0 stability with an unenforceable perf budget.
2. **Use the NFR thresholds directly as the CI gate** — rejected. Too tight; would flake on noisy runners. (This is what ADR-013 § 8 originally feared.)
3. **Migrate to a self-hosted runner immediately** — rejected for this WI. Self-hosted runner setup is operationally heavy (security, maintenance). If 1.5× p99 calibration proves insufficient post-1.0.0, *then* we migrate.
4. **Track perf in a regression DB instead of a gate** — rejected for this WI. Good idea, but a 1.x backlog item. We need a gate first.

---

### Cross-references

- ADR-013 § 8 (predecessor)
- FB-014-001 / FB-014-002 (origin)
- `docs/backlog/017-deferred-from-realtime-hardening.md`
- `benchmarks/bench_reverb.py`
- `benchmarks/scripts/calibrate_bench_reverb.py` (new in S2)
- `.github/workflows/ci.yml`

---

### Merged: Reverb benchmark CI job is advisory (`continue-on-error: true`) (was ADR-013 § 8)

**Status**: Accepted
**Date**: 2026-05-19
**Deciders**: Solution Architect (autonomous)

### Context

WI-014 introduces `benchmarks/bench_reverb.py` to measure:

- NFR-013-001 — publish-to-subscribe local fan-out p99 ≤ 5 ms
- NFR-013-003 — resident memory ≤ 64 MiB for 1000 connections / 100 channels

A new CI job `bench-reverb` runs the benchmark on every push to `main`. The question is whether the job should **block merge on budget miss** (hard gate) or **report and continue** (advisory).

### Decision

`bench-reverb` is **advisory**: `continue-on-error: true`, mirrors the existing `benchmark` job (`bench_foundations.py`).

```yaml
- name: Run reverb benchmarks
  run: uv run python benchmarks/bench_reverb.py | tee bench-reverb-output.txt
  continue-on-error: true
```

The script itself still exits non-zero on budget miss — that signal feeds the CI logs and the uploaded artifact. The `continue-on-error: true` only prevents the job's red status from blocking merges.

### Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Hard gate (`continue-on-error: false`) | Forces immediate attention to regressions | Shared GitHub Actions runners are noisy — p99 latency can vary ±30% across runs. False reds will quickly desensitise reviewers and erode trust in the gate. | Rejected for now |
| Advisory + alert on threshold breach via separate workflow | Loud signal without blocking | Adds bot/notification infra not currently in arvel CI; out of scope for WI-014 | Rejected — premature |
| **Advisory** (`continue-on-error: true`) | Captures regressions in CI logs + artifacts; matches existing `benchmark` job; lets us collect baseline first before tightening | Doesn't force action on regression | **Accepted** |
| Skip the benchmark in CI entirely | No flake risk | Loses the regression-detection point of having a benchmark | Rejected |

### Consequences

#### Positive
- Consistent with existing `benchmark` job — one policy, easy to understand
- Lets us collect baseline numbers across many commits before debating threshold-tightening
- Zero risk of false-red blocking unrelated PRs

#### Negative
- Real regressions can land unnoticed unless reviewers actively check the artifact
- Mitigated by FB-014-001 (file in Stage 6 ops report): after ~30 days of baselines, evaluate whether to promote to a hard gate as part of WI-017 Hardening

#### Neutral
- Future Hardening WI (WI-017) is the natural place to tighten this gate, alongside `bench_foundations.py`

### Related

- SAD-014 § 2.4, § 2.5
- PRD-014 FR-014-013, NFR-014-003, NFR-014-004, NFR-014-008
- Existing `benchmark` job in `.github/workflows/ci.yml` (the `bench_foundations.py` runner) — pattern this ADR formalises

---

## Subsumes

This ADR absorbs the following ADRs in the WI-arvel-005 consolidation pass (2026-06-07). The original files are deleted; their decision text is preserved verbatim above in the corresponding `§` sections.

| Old | Date | Subject | New location |
|---|---|---|---|
| ADR-105 | 2026-05-18 | `Broadcaster` Protocol + Driver Layout | § 1 |
| ADR-106 | 2026-05-18 | `Broadcast.channel()` Registry — Exact Pattern Matching, No Wildcards | § 2 |
| ADR-107 | 2026-05-18 | `ShouldBroadcast` is a Mixin on `Event`, Not a Separate Listener Type | § 3 |
| ADR-108 | 2026-05-18 | Reverb is Single-Event-Loop + Redis Pub/Sub Horizontal Scale | § 4 |
| ADR-109 | 2026-05-18 | Pusher Protocol v7 — What We Implement, What We Don't | § 5 |
| ADR-110 | 2026-05-18 | Channel-Auth HMAC-SHA256 Signature Scheme | § 6 |
| ADR-111 | 2026-05-18 | `BroadcasterFake` Lives Under `arvel.testing.broadcasting` | § 7 |
| ADR-112 | 2026-05-19 | Promote `bench-reverb` from advisory to hard CI gate | § 8 |
