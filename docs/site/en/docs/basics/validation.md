# Validation

Validation in Arvel splits into two lanes: **FastAPI/Pydantic** for typed request bodies and parameters, and the **FormRequest + Validator** stack when you want Laravel-style rule lists, async database rules, conditional logic, and centralized error messages. Both can coexist—pick FormRequest when authorization and rule composition belong with the payload.

## `FormRequest`

Subclass `FormRequest` and implement:

- `authorize(request) -> bool` — return `False` to abort with `AuthorizationFailedError`
- `rules() -> dict[str, list[Rule | AsyncRule]]` — field names to rule objects
- optionally `messages() -> dict[str, str]` — keys like `"email.Required"` overriding defaults
- optionally `after_validation(data) -> dict` — normalize or enrich validated data

Call `await form.validate_request(request=request, data=payload)` from your endpoint (often via a dependency) to run the pipeline in order: authorize, validate, then post-process.

```python
from arvel.validation import FormRequest, RequiredIf


class NonEmpty:
    """Example synchronous rule implementing the Rule protocol."""

    def passes(self, attribute: str, value: object, data: dict[str, object]) -> bool:
        return value is not None and str(value).strip() != ""

    def message(self) -> str:
        return "This field is required."


class StoreUserRequest(FormRequest):
    def authorize(self, request: object) -> bool:
        return True

    def rules(self) -> dict[str, list[object]]:
        return {
            "name": [NonEmpty()],
            "company_name": [RequiredIf("account_type", "business")],
        }


async def run_validation(raw: dict[str, object]) -> dict[str, object]:
    req = StoreUserRequest()
    return await req.validate_request(request=None, data=raw)
```

## The `Validator` engine

`Validator.validate(data, rules, messages=None)` walks each field’s rules sequentially. When a rule fails, it collects a `FieldError` with `field`, `rule`, and `message`. If any errors exist, it raises `ValidationError` with the full list—handy for APIs that want to return structured 422 payloads from your own handler.

## `Rule` and `AsyncRule`

- **Synchronous rules** implement `passes(attribute, value, data) -> bool` and `message() -> str`.
- **Async rules** return awaitable booleans from `passes`—perfect for I/O-bound checks.

The validator awaits async results automatically.

## Database rules: `Unique` and `Exists`

`Unique` and `Exists` perform parameterized SQLAlchemy queries against table/column names you provide. They require an `AsyncSession` in the rule instance—typically constructed in a factory that closes over the current request’s session.

```python
from arvel.validation.rules.database import Exists, Unique


def rules_for_create(session):
    return {
        "email": [
            Required(),
            Unique("users", "email", session=session),
        ],
        "organization_id": [
            Exists("organizations", "id", session=session),
        ],
    }
```

Never interpolate raw SQL; these rules use SQLAlchemy Core expressions under the hood.

## Conditional rules

`ConditionalRule` subclasses expose `condition_met(data)`. If the condition is false, the validator **skips the rest of the rules on that field**—the same short-circuit behavior Laravel developers expect. Built-ins include `RequiredIf`, `RequiredUnless`, `RequiredWith`, and `ProhibitedIf` (exported from `arvel.validation`).

```python
from arvel.validation import RequiredIf


def rules(self) -> dict[str, list[object]]:
    return {
        "company_name": [RequiredIf("account_type", "business")],
    }
```

## Custom rules

Implement the `Rule` or `AsyncRule` protocol: name your class clearly (`PassesCompanyPolicy`), implement `passes` and `message`, and add it to the rule list. For composite logic, compose smaller rules rather than growing a single mega-rule.

## Error messages

Override messages with `FormRequest.messages()` using keys `"field.RuleName"` (for example `"email.Email"`). The validator resolves messages after a failure, preferring your map, then the rule’s `message()`, then a sensible default.

`ValidationError.to_dict()` produces a structured payload with `message` and `errors` arrays—ideal for JSON responses that mirror server-side validation UX.

## FastAPI overlap

When you only need schema validation, Pydantic models on the endpoint are enough. Reach for `FormRequest` when the same class should answer authorization, multi-field conditional rules, database lookups, and shared message catalogs—exactly where Laravel’s `FormRequest` shines.
