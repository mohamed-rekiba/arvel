# ADR-096: Job class allowlist for deserialization safety

**Status**: Accepted
**Date**: 2026-05-18

## Context

Job deserialization requires mapping a string (`job_class: "app.jobs.send_welcome.SendWelcomeEmail"`)
back to a Python class. A naive `importlib.import_module(module) + getattr(class_name)` on an
untrusted string is an OWASP A05 (Injection) vector — an attacker who can write to the queue could
instantiate arbitrary classes.

## Options

| Option | Pros | Cons |
|---|---|---|
| A: Allowlist registry (import-time) | Strong security guarantee; mypy/pyright can see registered types | Requires jobs to be imported by the application at startup |
| B: Dynamic importlib.import_module | Zero registration ceremony | Arbitrary class instantiation from attacker-controlled strings |
| C: pickle | Compact | pickle is a known arbitrary code execution vector — forbidden |

## Decision

**Option A — allowlist registry**. A `JobRegistry` (dict `str → type[Job]`) is populated at import
time when job modules are imported (similar to how Django's app registry works). The worker looks up
`envelope.job_class` in the registry; unknown classes produce a `FailedJob` row with
`error: "Unknown job class"` — they never execute.

Registration is automatic: any `Job` subclass triggers `__init_subclass__` to add itself to the
registry. App code just imports the job class (or the module containing it) before the worker starts.

## Consequences

- **Gain**: Prevents deserialization-based code injection (OWASP A05).
- **Accept**: All job classes must be imported before the worker dispatches them. `bootstrap/providers.py`
  or an explicit import in `bootstrap/app.py` covers this.
- **Risk**: Registry grows unbounded in long-lived processes — mitigated by the fact that job classes
  are small Python objects and there are typically few of them.
