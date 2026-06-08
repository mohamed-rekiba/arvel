# Validation

<a name="introduction"></a>
## Introduction

Arvel provides several approaches to validate your application's incoming data. The most common is to declare validation requirements on a "form request" class and let the framework run them before your handler ever executes — invalid input produces a structured `422` response automatically, and your handler only runs against data you trust.

<a name="validation-in-two-layers"></a>
## Validation in Two Layers

Validation in Arvel happens in two complementary layers, and understanding the split is the key to using it well:

1. **The Pydantic layer** handles *shape and type* at parse time: which fields exist, their types, lengths, ranges, patterns. This runs when FastAPI parses the request body into your payload model.
2. **The rules layer** handles checks Pydantic can't do at parse time — *database* checks (does this email already exist?), *file* checks (is this an image of the right dimensions?), *cross-field* comparisons (does `password_confirmation` match?), and rich Laravel-parity rules for apps that want their validation expressed as rule strings.

A form request ties both layers together and adds an authorization check.

> [!TIP]
> Both layers are valid choices for shape and type checks. Pydantic shines when the payload is already a typed model (FastAPI route handlers); rule strings shine when validation is dynamic or driven by config. Pick whichever fits the call site — the rules layer now covers the common Laravel rules (`string`, `integer`, `numeric`, `email`, `url`, `min`, `max`, `in`, `regex`, `confirmed`, etc.) without falling back to "Unknown validation rule".

<a name="form-request-validation"></a>
## Form Request Validation

For more complex validation scenarios, you may wish to create a "form request". Form requests are custom classes that encapsulate their own validation and authorization logic. A `FormRequest[T]` wraps a parsed Pydantic payload of type `T`.

<a name="creating-form-requests"></a>
### Creating Form Requests

Declare the payload as a Pydantic model, subclass `FormRequest`, and use the form request as a handler parameter:

```python
from typing import Any

from pydantic import BaseModel, Field
from arvel.http.requests import FormRequest
from arvel.routing import Route


class StoreUserPayload(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    code: str


class StoreUserRequest(FormRequest[StoreUserPayload]):
    async def authorize(self, request: Any) -> bool:
        return True

    def rules(self) -> dict[str, str | list[str]]:
        return {
            "email": "required|unique:users,email",
            "code": "required|digits:6",
        }


@Route.post("/api/users")
async def store(form: StoreUserRequest) -> dict:
    data = form.validated()        # the typed StoreUserPayload
    return data.model_dump()
```

That's all that's needed. When the handler is called, the framework has already parsed, validated, and authorized the request. There's no validation code in the handler at all.

<a name="the-form-request-lifecycle"></a>
### The Form Request Lifecycle

When a route declares a `FormRequest` parameter, the framework runs these steps **in order** before invoking your handler:

1. **Pydantic validation.** FastAPI parses the request body into the payload model. A malformed body fails here and returns `422` before anything else runs.
2. **Rules.** `rules()` runs against the parsed payload. Any failure raises `ValidationException` (`422`).
3. **Authorization.** `authorize()` runs. Returning `False` raises `AuthorizationException` (`403`).
4. **Handler.** Your handler receives the fully validated form request.

Because rules run before authorization, your `authorize()` method can assume the payload is structurally valid.

<a name="authorizing-form-requests"></a>
### Authorizing Form Requests

The form request also contains an `authorize` method. Within this method, you may check whether the authenticated user actually has authority to perform the action. The raw request is passed in so you can read the authenticated user from it:

```python
class UpdatePostRequest(FormRequest[UpdatePostPayload]):
    async def authorize(self, request: Any) -> bool:
        user = getattr(request.state, "user", None)
        return user is not None and user.is_admin
```

> [!WARNING]
> `authorize()` **defaults to `False`** — deny by default. You must override it to let requests through. This is deliberate (a forgotten override fails closed, not open), but it's the single most common surprise when writing your first form request.

If `authorize` returns `False`, a `403` response is returned automatically and your handler does not execute.

<a name="accessing-the-validated-data"></a>
### Accessing the Validated Data

Once the request passes validation, retrieve the typed payload with `validated()`:

```python
@Route.post("/api/users")
async def store(form: StoreUserRequest) -> dict:
    payload = form.validated()      # an instance of StoreUserPayload
    return {"email": payload.email}
```

To access the raw `Request` inside your handler (for headers, the authenticated user, etc.), add a separate `request: Request` parameter alongside the form request:

```python
@Route.post("/api/users")
async def store(form: StoreUserRequest, request: Request) -> dict:
    ...
```

<a name="the-pydantic-layer"></a>
## The Pydantic Layer

Put type and shape constraints on the payload model with Pydantic's `Field`. These run before any rule and cover the vast majority of "validation" most people reach for:

```python
from pydantic import BaseModel, Field


class StoreUserPayload(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r".+@.+")
    name: str = Field(min_length=1, max_length=120)
    age: int = Field(ge=0, le=150)
```

Reserve the [rules layer](#available-validation-rules) for what Pydantic genuinely can't express — database lookups and file inspection.

<a name="available-validation-rules"></a>
## Available Validation Rules

The following rules are available in the `rules()` layer. Rules are written as pipe-delimited strings (`"required|digits:6"`) or as a list (`["required", "digits:6"]`). Parameters follow a colon and are comma-separated.

### Presence & emptiness

| Rule | Form | Purpose |
|---|---|---|
| [`required`](#rule-required) | `required` | Field must be present and non-empty. |
| `nullable` | `nullable` | Marker rule that always passes; pair with others to signal "null is OK". |
| `present` | `present` | Field key must exist in the payload, even if its value is empty/null. |
| `filled` | `filled` | When present, the field must have a non-empty value. |
| `prohibited` | `prohibited` | Field must be absent or empty. |
| [`bail`](#rule-bail) | `bail` | Stop running rules for this field at the first failure. |

### Conditional presence

These make a field required based on the value or presence of other fields. They only fail when the trigger condition holds **and** the field is empty.

| Rule | Form | Purpose |
|---|---|---|
| `required_if` | `required_if:other,val,...` | Required when `other` equals one of the listed values. |
| `required_unless` | `required_unless:other,val,...` | Required unless `other` equals one of the listed values. |
| `required_with` | `required_with:f1,f2,...` | Required when **any** of the listed fields are present. |
| `required_with_all` | `required_with_all:f1,f2,...` | Required when **all** of the listed fields are present. |
| `required_without` | `required_without:f1,f2,...` | Required when **any** of the listed fields are missing. |
| `required_without_all` | `required_without_all:f1,f2,...` | Required when **all** of the listed fields are missing. |

### Types & format

| Rule | Form | Purpose |
|---|---|---|
| `string` | `string` | Value must be a string. |
| `integer` | `integer` | Value must be an integer (or numeric string). |
| `numeric` | `numeric` | Value must be a number (or numeric string). |
| `boolean` | `boolean` | Accepts truthy/falsy: `True/False`, `1/0`, `"yes"/"no"`, `"on"/"off"`. |
| `accepted` | `accepted` | Value must be one of `True`, `1`, `"1"`, `"true"`, `"yes"`, `"on"` (checkbox-style). |
| `email` | `email` | RFC-friendly email format. |
| `url` | `url` | Value must be a URL. |
| `uuid` | `uuid` | Value must be a valid UUID. |
| `ip` / `ipv4` / `ipv6` | `ip` | IP address (any family / IPv4 only / IPv6 only). |
| `json` | `json` | Value must be a valid JSON string. |
| `alpha` | `alpha` | Letters only. |
| `alpha_num` | `alpha_num` | Letters and digits. |
| `alpha_dash` | `alpha_dash` | Letters, digits, `-`, `_`. |

### Strings & patterns

| Rule | Form | Purpose |
|---|---|---|
| [`digits`](#rule-digits) | `digits:n` | A string of exactly *n* digits. |
| `regex` | `regex:pattern` | Value matches the given regex. |
| `not_regex` | `not_regex:pattern` | Value does NOT match the regex. |
| `starts_with` | `starts_with:foo,bar` | Value starts with one of the listed prefixes. |
| `ends_with` | `ends_with:foo,bar` | Value ends with one of the listed suffixes. |
| `in` | `in:foo,bar,baz` | Value is one of the listed options. |
| `not_in` | `not_in:foo,bar,baz` | Value is none of the listed options. |

### Size & range

`min`, `max`, `between`, and `size` measure strings/lists/dicts by `len()` and numbers by value.

| Rule | Form | Purpose |
|---|---|---|
| `min` | `min:n` | At least *n* (length or value). |
| `max` | `max:n` | At most *n*. |
| `between` | `between:a,b` | In the inclusive range `[a, b]`. |
| `size` | `size:n` | Exactly *n*. |

### Dates

Date rules accept ISO-8601 strings (`2026-01-15`, `2026-01-15T10:30:00`) and `date`/`datetime` objects. The bound for `before`/`after` can be a literal date, another field name, or `today`/`now`. Naive values are read as UTC so comparisons are consistent.

| Rule | Form | Purpose |
|---|---|---|
| `date` | `date` | Value parses as a date. |
| `date_format` | `date_format:%d/%m/%Y` | Value matches the given `strptime` format. |
| `before` | `before:2026-06-01` | Date is before the bound. |
| `after` | `after:start_date` | Date is after the bound (here, the `start_date` field). |
| `before_or_equal` | `before_or_equal:today` | Date is on or before the bound. |
| `after_or_equal` | `after_or_equal:today` | Date is on or after the bound. |

### Cross-field comparisons

| Rule | Form | Purpose |
|---|---|---|
| `confirmed` | `confirmed` | A paired `<field>_confirmation` exists with the same value. |
| `same` | `same:other` | Value equals the value at `other`. |
| `different` | `different:other` | Value differs from the value at `other`. |

### Database & files

| Rule | Form | Purpose |
|---|---|---|
| [`exists`](#rule-exists) | `exists:table,column` | The value must exist in a database column. |
| [`unique`](#rule-unique) | `unique:table,column,...` | The value must not already exist. |
| [`mimes`](#rule-mimes) | `mimes:ext,...` | An uploaded file of an allowed type. |
| [`dimensions`](#rule-dimensions) | `dimensions:key=n,...` | An image meeting size constraints. |

> [!NOTE]
> An unknown rule name doesn't raise — it adds a `"Unknown validation rule '<name>'."` detail to the error response. Most rules are no-ops on `None` so they layer cleanly with `nullable`.

<a name="rule-required"></a>
### required

The field under validation must be present and not "empty". A value is empty when it's `None`, an empty string, an empty list, or an empty dict.

```python
{"name": "required"}
```

<a name="rule-bail"></a>
### bail

Stop running the rest of a field's rules after the first one fails. Put it first in the chain. Without `bail`, every rule runs and you get every failure for that field; with it, you get just the first.

```python
{"code": "bail|integer|min:5"}
```

`bail` only affects the field it appears on, and it never produces an error itself.

<a name="rule-digits"></a>
### digits:_n_

The field under validation must be numeric and have an exact length of *n* digit characters. The length parameter is required.

```python
{"pin": "required|digits:4"}
```

A `None` value is skipped (combine with `required` to forbid it).

<a name="rule-exists"></a>
### exists:_table_,_column_

The field under validation must exist in the given database table and column. Both the table and column are required:

```python
{"author_id": "exists:users,id"}
```

This runs an async query against the active database session. A `None` value is skipped.

> [!NOTE]
> `exists` (and `unique`) need an active database session, which the normal request path provides. They check a single `column == value` equality — there's no support for additional `WHERE` conditions. Run them outside a request (a console command or job) and you'll get a clear error telling you to wrap the call in `async with DB.transaction():`.

<a name="rule-unique"></a>
### unique:_table_,_column_,_except_,_except_column_

The field under validation must not exist in the given table and column. This is the classic "is this email already taken?" check:

```python
{"email": "unique:users,email"}
```

When updating a record, you'll want to ignore the row being updated. Pass the value to ignore (and, optionally, the column to compare it against — defaults to `id`):

```python
# Allow the current user (id 42) to keep their own email.
{"email": "unique:users,email,42,id"}
```

A `None` value is skipped.

<a name="rule-mimes"></a>
### mimes:_ext_,...

The uploaded file under validation must have a MIME type corresponding to one of the listed extensions. Provide at least one extension:

```python
{"avatar": "mimes:png,jpg"}
```

The rule matches by file extension or by a known MIME type. Recognized image types are `jpg`/`jpeg` → `image/jpeg`, `png` → `image/png`, `gif` → `image/gif`, and `webp` → `image/webp`. A `None` value is skipped.

<a name="rule-dimensions"></a>
### dimensions:_key_=_n_,...

The image file under validation must satisfy the listed dimension constraints. Constraints are written as `key=value` pairs:

```python
{"avatar": "dimensions:min_width=100,min_height=100,max_width=1024,max_height=1024"}
```

Supported keys: `min_width`, `max_width`, `min_height`, `max_height`, `width` (exact), and `height` (exact). The rule reads the image bytes and parses PNG and JPEG headers. A non-image value fails with "must be an image"; a `None` value is skipped.

Rules combine naturally:

```python
def rules(self) -> dict[str, str | list[str]]:
    return {
        "email": "required|unique:users,email",
        "avatar": "mimes:png,jpg|dimensions:max_width=1024,max_height=1024",
    }
```

<a name="nested-and-wildcard-fields"></a>
## Nested and Wildcard Fields

Rules can target nested data with dot notation, and validate every entry of an
array with the `*` wildcard — matching Laravel.

```python
def rules(self) -> dict[str, str | list[str]]:
    return {
        "address.city": "required|string",       # nested object
        "items": "required",                       # the array itself
        "items.*.id": "required|integer",          # every element's id
        "items.*.qty": "integer|min:1",
    }
```

Given `{"items": [{"id": 1, "qty": 2}, {"qty": 0}]}`, the failures come back
keyed by the concrete path:

```json
[
  {"field": "items.1.id", "issue": "The items.1.id field is required."},
  {"field": "items.1.qty", "issue": "The items.1.qty must be at least 1."}
]
```

Two behaviors worth knowing:

- A **wildcard only iterates entries that exist** — if `items` is missing entirely,
  `items.*.id` rules simply don't run (no false "required" errors).
- A **non-wildcard nested path always validates**, even when the parent is
  missing — `address.city: required` fails whether `address` is absent or present
  without a `city`.

Explicit indices (`items.0.id`) and dict wildcards (`meta.*.value`) work too.
Custom messages can be keyed by the wildcard form (`items.*.id.required`) or by a
concrete path (`items.1.id.required`) — the concrete key wins when both exist.

<a name="conditional-rules"></a>
## Conditional Rules

Sometimes you want to run validation checks against a field only if that field is present, or only when another field has a certain value. Add conditional rules from the `with_validator` hook on your form request. The validator's `sometimes` method takes the field, the rules to apply, and a callback that receives the full data and returns whether the rules should apply:

```python
from arvel.validation.validator import Validator


class StorePaymentRequest(FormRequest[StorePaymentPayload]):
    def with_validator(self, validator: Validator) -> None:
        validator.sometimes(
            "card_number",
            "required|digits:16",
            lambda data: data.get("payment_method") == "card",
        )
```

The `card_number` rules only run when `payment_method` is `"card"`.

<a name="rule-builders"></a>
## Rule Builders

`Rule` provides typed helpers that build rule-expression strings, so you don't have to hand-format the comma-joined parameters. They slot straight into the same `rules()` dict:

```python
from arvel.validation import Rule


def rules(self) -> dict[str, str | list[str]]:
    return {
        "role": Rule.in_("admin", "editor", "viewer"),
        "email": Rule.unique("users", "email", ignore=self.user_id),
        "author_id": Rule.exists("users", "id"),
        "card_number": ["required", Rule.required_if("payment", "card")],
    }
```

Available builders: `Rule.in_`, `Rule.not_in`, `Rule.exists`, `Rule.unique`, `Rule.required_if`, `Rule.required_unless`. Values are comma-joined, so a value containing a comma isn't supported — reach for a [custom rule](#custom-rules) in that case.

<a name="custom-rules"></a>
## Custom Rules

Register your own rule once at startup and use it by name anywhere. A rule handler takes `(field, value, params, data, request)` and returns an error message on failure or `None` on success — sync or async:

```python
from arvel.validation import register_rule


def rule_even(field, value, params, data, request):
    if isinstance(value, int) and value % 2 == 0:
        return None
    return f"The {field} must be even."


register_rule("even", rule_even)

# Now usable like any built-in:
{"quantity": "required|integer|even"}
```

<a name="customizing-messages-and-attributes"></a>
## Customizing Messages and Attributes

Override `messages()` to customize the error text for a specific field/rule pair, keyed as `field.rule`. Override `attributes()` to provide human-friendly field labels that get substituted into messages:

```python
class StoreUserRequest(FormRequest[StoreUserPayload]):
    def rules(self) -> dict[str, str | list[str]]:
        return {"email": "required|unique:users,email"}

    def messages(self) -> dict[str, str]:
        return {"email.unique": "That email is already registered."}

    def attributes(self) -> dict[str, str]:
        return {"email": "email address"}
```

<a name="manual-validation"></a>
## Manual Validation

To validate data outside a form request, construct a `Validator` directly. Its `validate` method returns a list of error details — an empty list means the data is valid:

```python
from arvel.validation.validator import Validator

details = await Validator({"email": "a@b.com"}).validate({"email": "unique:users,email"})

if details:
    # [{"field": "email", "issue": "The email has already been taken."}]
    ...
```

<a name="the-validation-error-response"></a>
## The Validation Error Response

A failed validation produces a `ValidationException` (`422`) whose body follows the framework's standard [error envelope](error-handling.md):

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Validation failed.",
    "details": [
      {"field": "email", "issue": "The email has already been taken."}
    ]
  }
}
```

FastAPI's body-parsing errors (the Pydantic layer) are normalized into the **same** shape, so the client sees one consistent error format regardless of which layer rejected the input.

<a name="generating-form-requests"></a>
## Generating Form Requests

Scaffold a form request with:

```bash
arvel make:request StoreUserRequest
```
