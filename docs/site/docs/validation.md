# Validation

Arvel relies on **Pydantic** for input validation. Every form request, every API resource, every config schema is a Pydantic model — so the validation rules you learn here apply uniformly across the framework.

## Basic validation

For most endpoints, you'll wrap input in a `FormRequest`:

```python
from pydantic import BaseModel, EmailStr, Field
from arvel import FormRequest, Route


class StoreUser(FormRequest[StoreUserPayload]):
    async def authorize(self, request) -> bool:
        return True


class StoreUserPayload(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    age: int = Field(ge=13, le=130)


@Route.post("/users")
async def create(form: StoreUser) -> dict:
    payload = form.validated()
    return {"created": payload.email}
```

When the request body fails validation, Arvel returns `422 Unprocessable Entity` with a structured body:

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Request body failed validation.",
    "details": [
      {
        "field": "email",
        "issue": "value is not a valid email address"
      },
      {
        "field": "age",
        "issue": "Input should be greater than or equal to 13"
      }
    ]
  }
}
```

## Common constraints

```python
from typing import Annotated
from pydantic import BaseModel, Field, EmailStr, HttpUrl, conint


class Example(BaseModel):
    # String length
    name: Annotated[str, Field(min_length=1, max_length=100)]

    # Numeric range
    age: Annotated[int, Field(ge=0, le=150)]

    # Regex
    slug: Annotated[str, Field(pattern=r"^[a-z0-9-]+$")]

    # Email
    email: EmailStr

    # URL
    website: HttpUrl | None = None

    # Enum
    role: Literal["admin", "user", "guest"] = "user"

    # Lists with size constraints
    tags: Annotated[list[str], Field(min_length=1, max_length=5)]
```

For the full catalog, see [Pydantic field constraints](https://docs.pydantic.dev/2/concepts/fields/).

## Custom validators

Use `field_validator` for field-level logic, `model_validator` for cross-field checks:

```python
from pydantic import BaseModel, field_validator, model_validator


class CreateOrder(BaseModel):
    quantity: int
    discount_code: str | None = None
    customer_age: int

    @field_validator("quantity")
    @classmethod
    def quantity_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be positive")
        return value

    @model_validator(mode="after")
    def discount_requires_adult(self) -> "CreateOrder":
        if self.discount_code and self.customer_age < 18:
            raise ValueError("discount codes require customer to be 18+")
        return self
```

`mode="after"` runs after individual field validation; `mode="before"` runs first.

## Database-backed validation rules

Pydantic handles type and shape checks. For database and file constraints,
declare ``rules()`` on your ``FormRequest``:

```python
class StorePost(FormRequest[StorePostPayload]):
    async def authorize(self, request) -> bool:
        return True

    def rules(self) -> dict[str, str | list[str]]:
        return {
            "post_id": "exists:posts,id",
            "email": "unique:users,email",
            "avatar": "mimes:jpg,png",
            "photo": "dimensions:min_width=100,min_height=100",
        }

    def messages(self) -> dict[str, str]:
        return {"email.unique": "That email is already taken."}
```

Rules run server-side after the body parses and before ``authorize()``. Failures
return `422` with the same structured error envelope as Pydantic validation.

Update flows pass an except id to ``unique``:

```python
{"email": f"unique:users,email,{user_id},id"}
```

### Conditional rules with `sometimes`

Use ``FormRequest.with_validator()`` to apply rules only when a callback returns
``True``:

```python
from arvel.validation import Rule, Validator


class PayForm(FormRequest[PayPayload]):
    def with_validator(self, validator: Validator) -> None:
        validator.sometimes(
            "card_number",
            "required|digits:16",
            lambda data: data.get("payment") == "card",
        )
        # or: validator.add(Rule.sometimes("card_number", ["required", "digits:16"], ...))
```

When the condition is ``False``, the field is skipped entirely — even if it's
missing or invalid.

For one-off checks without the rules DSL, you can still query in the handler
after ``form.validated()`` — but prefer ``rules()`` when the constraint maps to
a string rule.

## Conditional fields

Use `Annotated` with `Discriminator` for tagged unions:

```python
from typing import Annotated, Literal, Union
from pydantic import BaseModel, Discriminator, Tag


class CreditCardPayment(BaseModel):
    method: Literal["credit_card"] = "credit_card"
    card_number: str
    expiry: str


class BankTransferPayment(BaseModel):
    method: Literal["bank_transfer"] = "bank_transfer"
    iban: str


Payment = Annotated[
    Union[
        Annotated[CreditCardPayment, Tag("credit_card")],
        Annotated[BankTransferPayment, Tag("bank_transfer")],
    ],
    Discriminator("method"),
]


class CreateOrder(BaseModel):
    amount: int
    payment: Payment
```

The discriminator lets Pydantic pick the right shape and surface clean error messages tied to the variant.

## Strict mode

By default, Pydantic coerces types where it makes sense (string → int when the string is a number). For APIs where you want strict types, enable strict mode:

```python
class StrictPayload(BaseModel):
    model_config = {"strict": True}

    age: int  # rejects "30" — must be the integer 30
```

## Validation in places other than HTTP

Pydantic validation runs anywhere you call `Model(**data)` or `Model.model_validate(data)`. The framework uses it for:

- Form requests (HTTP body)
- Query parameters (FastAPI auto-validates)
- Config (`ArvelSettings` subclasses)
- Job payloads (`Job` subclasses)
- Event payloads (`Event` subclasses)
- Mailable / Notification metadata

Consistency means once you've learned Pydantic, you've learned how Arvel validates input across every layer.

## Where to next?

- [Requests](requests.md) — form requests in detail.
- [Errors](errors.md) — how validation errors become HTTP responses.
- [Authorization](authorization.md) — gates and policies for permission checks.
