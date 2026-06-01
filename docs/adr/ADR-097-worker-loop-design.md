# ADR-097: queue:work worker loop design (asyncio + SIGTERM drain)

**Status**: Accepted
**Date**: 2026-05-18

## Context

The `queue:work` command needs to run as a long-lived process, poll or block on the queue, and exit
cleanly when asked to stop (e.g., container orchestration sends SIGTERM before shutdown).

## Options

| Option | Pros | Cons |
|---|---|---|
| A: asyncio loop + signal handler (drain) | Native asyncio; clean SIGTERM drain; single codebase path | Slightly more complex signal setup |
| B: Taskiq's built-in worker command | Zero code for Taskiq driver | Only works for Taskiq — database/redis/sync drivers can't use it |
| C: threading.Thread + queue.Queue | Simpler | Blocks GIL; not async-native; incompatible with async handle() |

## Decision

**Option A — single asyncio loop per driver**, with a `_stop` `asyncio.Event` set on `SIGTERM`.

Loop:
```
while not _stop.is_set():
    envelope = await driver.pop_blocking(queue, timeout=sleep_interval)
    if envelope:
        await _process(envelope)
    # else: poll interval elapsed, check stop flag
```

On `SIGTERM`: set `_stop`, let the current job finish, then exit. The `timeout` on `pop_blocking`
(default 3s) ensures the stop event is checked at least every 3 seconds even on blocking drivers.

For the `taskiq` driver: `queue:work` starts Taskiq's broker and delegates to Taskiq's own async
task reception mechanism, but still wraps it in the same SIGTERM-aware loop.

## Consequences

- **Gain**: Works for all four drivers with one code path; clean shutdown guaranteed.
- **Accept**: poll interval adds up-to-3s latency on shutdown. Acceptable for worker processes.
- **Risk**: Very long-running jobs delay shutdown beyond SIGTERM — mitigated by `job.timeout`.
