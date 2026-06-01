# Validation

<a name="introduction"></a>
## Introduction

Arvel provides several approaches to validate your application's incoming data. The most common is to declare validation requirements on a "form request" class and let the framework run them before your handler ever executes — invalid input produces a structured `422` response automatically, and your handler only runs against data you trust.

<a name="validation-in-two-layers"></a>
## Validation in Two Layers

Validation in Arvel happens in two complementary layers, and understanding the split is the key to using it well:

1. **The Pydantic layer** handles *shape and type*: which fields exist, their types, lengths, ranges, patterns, required-ness at the structural level. This runs when FastAPI parses the request body into your payload model.
2. **The rules layer** handles checks Pydantic can't do on its own — primarily *database* checks (does this email already exist?) and *file* checks (is this an image of the right dimensions?).

A form request ties both layers together and adds an authorization check.

> [!WARNING]
> The rules layer implements a **small, specific set** of rules — see [Available Validation Rules](#available-validation-rules). Type and shape checks (string, integer, length, email format, min/max) belong on the **Pydantic payload model**, not in `rules()`. Writing `string`, `numeric`, `min:`, or `max:` in `rules()` produces an "Unknown validation rule" error rather than a check. Express those with Pydantic `Field(...)` instead.

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

| Rule | Form | Purpose |
|---|---|---|
| [`required`](#rule-required) | `required` | The field must be present and non-empty. |
| [`digits`](#rule-digits) | `digits:n` | A string of exactly *n* digits. |
| [`exists`](#rule-exists) | `exists:table,column` | The value must exist in a database column. |
| [`unique`](#rule-unique) | `unique:table,column,...` | The value must not already exist. |
| [`mimes`](#rule-mimes) | `mimes:ext,...` | An uploaded file of an allowed type. |
| [`dimensions`](#rule-dimensions) | `dimensions:key=n,...` | An image meeting size constraints. |

> [!WARNING]
> An unknown rule name doesn't raise — it adds a `"Unknown validation rule '<name>'."` detail to the error response. If you see that message, you've used a rule that isn't in this table (likely a Laravel rule that belongs on the Pydantic model).

<a name="rule-required"></a>
### required

The field under validation must be present and not "empty". A value is empty when it's `None`, an empty string, an empty list, or an empty dict.

```python
{"name": "required"}
```

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
> `exists` (and `unique`) need an active database session, which the normal request path provides. They check a single `column == value` equality — there's no support for additional `WHERE` conditions.

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
