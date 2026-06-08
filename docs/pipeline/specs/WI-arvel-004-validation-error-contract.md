# WI-arvel-004 — Consistent, testable validation error contract

| | |
|---|---|
| **Module** | validation / http |
| **Complexity** | L2 | **Risk** | Tier 2 | **Data** | internal |
| **Autonomous** | yes | **Frontend** | no |
| **Research** | `.context/research/004-validation.md` (F1, F2) |
| **Review** | `requesting-code-review` — F1 detail-shape deviation confirmed (one endpoint); F2 test-helper gap confirmed |

## Problem

Arvel's default validation envelope is `{"error": {"code", "message", "details":
[{"field", "issue"}]}}`. Rule failures and the Pydantic-422 normalizer
(`exceptions.py:_handle_validation`) both emit `{"field", "issue"}` detail items.

**F1.** `auth/http/controller.py::reset_password` deviates — it raises `ValidationException`
with a **Pydantic-shaped** detail (`{"loc", "msg", "type"}`). A client parsing
`error.details[].field` / `.issue` (the documented contract) breaks on this one endpoint.

**F2.** The framework's own test helper `TestResponse.assert_json_validation_errors`
(via `testing/response.py::_extract_error_fields`) understands FastAPI (`detail[].loc`) and
Laravel (`errors{}`) shapes but **not** Arvel's native `error.details[].field` envelope, so
it can't assert against the framework's own validation responses.

## Spec Items → Verification

| ID | Spec item | Test | Status |
|---|---|---|---|
| SPEC-1 | `reset_password` on an invalid/expired token returns a 422 whose detail entry uses `{"field": "token", "issue": ...}` (canonical shape), not `{"loc","msg","type"}`. Both handlers pass `exc.details` through verbatim, so the fix holds for the error-bag (`error.details[]`) and RFC 7807 (`detail[]`) envelopes; the auth test_app is wired with the RFC 7807 handler, so the test reads `detail[0]`. | `test_auth/integration/test_controller.py::test_reset_password_invalid_token_uses_canonical_detail_shape` | PASS |
| SPEC-2 | `_extract_error_fields` recognizes the native `error.details[].field` envelope; `assert_json_validation_errors` passes against an Arvel default 422 body. | `tests/testing/test_response.py::TestJsonValidationErrors::test_recognises_arvel_error_details_shape` | PASS |
| SPEC-3 (X-cut: no regression) | Existing FastAPI/Laravel shape recognition and all auth-controller behavior unchanged. | `tests/testing/test_response.py` + `test_auth/integration/test_controller.py` (full, green) | PASS |
| SPEC-4 (X-cut: type safety) | mypy --strict + pyright clean; no new `Any` at the changed boundaries, no `# type: ignore`. | `mypy` + `pyright` | PASS |
| SPEC-5 (X-cut: lint) | ruff clean on changed files; full validation + http + testing suites green. | `ruff` + `pytest` | PASS |

## Root-cause fixes

- `auth/http/controller.py` — `reset_password`: emit
  `details=[{"field": "token", "issue": "Reset token is invalid or has expired."}]`,
  matching the framework's canonical detail shape.
- `testing/response.py` — `_extract_error_fields`: also walk `body["error"]["details"]`
  (native error-bag) and recognise `{field}` entries in a top-level `detail` list (RFC 7807),
  collecting each item's `field`, alongside the existing FastAPI `detail[].loc` and Laravel
  `errors{}` handling. Refactored into `_fields_from_detail_entry` / `_fields_from_detail_list`
  to keep cyclomatic complexity under the gate's limit.

## Deliberate design decisions

- Keep the `{error:{code,message,details:[{field,issue}]}}` envelope (greenfield — no need
  to match Laravel's `{message, errors}` byte-for-byte). The fix makes the envelope
  **uniform**, not Laravel-identical.
- The RFC 7807 `ProblemDetailsHandler` keeps `loc/msg/type` for its opt-in
  `application/problem+json` format — a separate, intentional shape, out of scope.

## Deferred (tracked)

- **F3** — `nullable` doesn't short-circuit other rules. Low impact (most rules self-skip
  null); risky edge behavior for `confirmed`/`same`. Separate WI if ever needed.
- **F4** — unknown rule soft-fails to the client instead of raising at dev time.
- **F5** — rules see only the Pydantic-parsed body (no raw input / query / path); deeper
  redesign.
- **F6** — `exists`/`unique` without an active session → 500 (arguably correct).
