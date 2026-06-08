# WI-arvel-008 — Worker cancellation must propagate, not fail the in-flight job

| | |
|---|---|
| **Module** | queue |
| **Complexity** | L2 | **Risk** | Tier 2 | **Data** | internal |
| **Autonomous** | yes | **Frontend** | no |
| **Research** | `.context/research/008-queue.md` (F1 fixed; F2 delete-on-pop + F3 taskiq deferred) |
| **Review** | F1 confirmed surgical; timeout path empirically distinct (`TimeoutError`, not `CancelledError`) |

## Problem

`Worker._process_one` caught `except (Exception, asyncio.CancelledError)`, so
**external worker cancellation** (graceful shutdown, `task.cancel()`, `SIGINT`)
was handled as a **job failure**:

1. `envelope.attempts += 1`, then the in-flight job was re-queued or written to
   the dead-letter queue.
2. The `CancelledError` was **swallowed** — the loop continued / the coroutine
   returned normally instead of unwinding. That violates the asyncio
   cancellation contract and means a cancelled worker wouldn't stop promptly.

A per-job timeout surfaces as `TimeoutError` (Python 3.11+, verified on 3.14),
not `CancelledError` — so the old `CancelledError → TimeoutError("Job timed out")`
conversion in the DLQ branch was dead code, and `CancelledError` only ever means
external cancellation.

## Spec Items → Verification

| ID | Spec item | Test | Status |
|---|---|---|---|
| SPEC-1 | Cancelling the worker mid-job propagates `CancelledError` (the worker stops). | `tests/test_queue/test_047_queue_reliability.py::TestStory7JobTimeout::test_external_cancellation_propagates_and_does_not_fail_job` | PASS |
| SPEC-2 | External cancellation does **not** count as a failed attempt or DLQ the job (`jobs_dead == 0`, `jobs_retried == 0`, DLQ empty). | same test | PASS |
| SPEC-3 | A real `handle()` exception still retries up to `tries`, then DLQs. | `...::TestStory*` (existing retry/DLQ tests) | PASS |
| SPEC-4 | A per-job `timeout` still marks the job failed (timeout → `TimeoutError` → `except Exception`). | `...::TestStory7JobTimeout::test_timeout_causes_job_to_fail` + `test_timeout_logs_job_class_and_timeout` | PASS |
| SPEC-5 (X-cut: types/lint) | mypy `--strict` + pyright clean; ruff clean on changed files; full queue suite green (231). | `mypy` + `pyright` + `ruff` + `pytest` | PASS |

## Root-cause fix

`queue/worker.py` — split the single catch into:

```python
except asyncio.CancelledError:
    raise                 # external cancellation — propagate, never a job failure
except Exception as exc:
    if isinstance(exc, TimeoutError):
        logger.warning("queue.job.timeout", ...)
    ...                   # attempts += 1 → retry/backoff or DLQ
```

Removed the now-dead `exc if not isinstance(exc, CancelledError) else
TimeoutError("Job timed out")` conversion in the DLQ branch (`TimeoutError` is
already an `Exception` and is reported verbatim).

## Deliberate design decisions

- **Re-raise `CancelledError`** rather than catch-and-stop: it's the only
  asyncio-correct way to unwind a cancelled task and lets the in-flight job stay
  unmarked (the queue, not the DLQ, owns its fate).
- **Rely on `TimeoutError` for timeouts** (3.11+ `wait_for` contract) instead of
  pattern-matching `CancelledError` — simpler and correct on 3.14.

## Deferred (tracked)

- **F2 (Critical)** — delete-on-pop / no visibility timeout in the database
  driver (at-most-once on worker crash). Needs reserve + visibility timeout +
  reaper — a dedicated architectural WI.
- **F3 (Medium)** — `Taskiq` driver `pop_blocking` ignores the poll timeout.
