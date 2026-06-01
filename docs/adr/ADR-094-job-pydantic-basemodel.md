# ADR-094: Job model — Pydantic BaseModel as the job primitive

**Status**: Accepted
**Date**: 2026-05-18

## Context

We need a typed, serializable unit of work. The wire format must support Pydantic validation on
deserialization (prevents invalid payloads from crashing the worker). Laravel uses PHP Serializable /
JSON — we need the Python equivalent that fits our strict-typing posture.

## Options

| Option | Pros | Cons |
|---|---|---|
| A: Pydantic BaseModel | Type-safe, validates on deserialize, model_dump/model_validate built-in, mypy/pyright-friendly | Slightly more ceremony than a plain dataclass |
| B: dataclass + manual JSON | Lighter weight | No validation on deserialize; not mypy-strict without extra work |
| C: msgspec Struct | Faster | Less ecosystem familiarity; no model_validate equivalent |

## Decision

Use **Option A — Pydantic BaseModel**. Consistent with every other typed Arvel primitive (FormRequest,
ArvelSettings, etc.). Validates payload on the worker side before `handle()` — malformed payloads fail
cleanly into `FailedJob` rather than crashing the worker.

Wire format: `JobEnvelope` dataclass with `job_class` (dotted path) + `payload` (model_dump output)
serialized as a single JSON string.

## Consequences

- **Gain**: Type-safe jobs; automatic payload validation; framework consistency.
- **Accept**: Jobs must be Pydantic models (slight constraint on job definition style).
- **Risk**: Deeply nested payload types need Pydantic model wrappers — mitigated by convention.
