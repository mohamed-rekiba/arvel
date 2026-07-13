# Validation

Never trust what arrives over the wire. Before a request body reaches your business logic, you want
to know it's shaped the way you expect — required fields present, an email that's actually an email,
an age that's a number in range. arvel gives you two complementary ways to enforce that: a rule-based
**`Validator`** for quick, dynamic checks (rules as `|`-delimited strings), and typed **`Schema`** /
**`FormRequest`** objects when you want the validated data to come back fully typed. Either way, bad
input becomes a clean `422` your app renders for the right client automatically. Validation is part
of the **core** — nothing to install.

## Validation quickstart

Build a `Validator` from the request data and a ruleset, then ask whether it `passes()`/`fails()`:

```python
from arvel.validation import Validator

validator = Validator(
    data=request.data,
    rules={
        "name": "required|string|max:255",
        "email": "required|email",
        "age": "nullable|integer|min:18",
    },
)

if validator.fails():
    return {"errors": validator.errors()}, 422

clean = validator.validated()  # only the validated fields
```

`errors()` returns a `dict[str, list[str]]` keyed by field; `validated()` returns just the fields
that had rules (a deliberate allow-list, so stray keys never leak through). You can also build one
through the [`Validator` facade](facades.md), which reads naturally and is swappable in tests:

```python
from arvel import Validator

validator = Validator.make(request.data, {"email": "required|email"})
```

## Displaying the validation errors

`validate()` returns the validated data or raises a `422` `ValidationException` carrying the error
dict — the framework's exception handler renders it to match the client, so you write it once:

```python
clean = Validator(request.data, {"email": "required|email"}).validate()
```

| Client | Signal | Response |
|--------|--------|----------|
| API / SPA | `Accept: application/json` (or none) | `422` with `{"message": ..., "errors": {...}}` |
| Inertia | `X-Inertia: true` | `422` with the same `{message, errors}` body |
| Browser | `Accept: text/html` | **redirect back** (`302`) with errors flashed to the session error bag |

So an API gets machine-readable per-field errors, while a browser is sent back to the form with
`errors` available to the template on the next request:

```html
{% if errors %}<ul>{% for field, msgs in errors.items() %}<li>{{ msgs[0] }}</li>{% endfor %}</ul>{% endif %}
```

The `errors` variable is put there by the **web** group's `ShareErrorsFromSession` middleware, which
reads the flashed error bag every request and shares it as `errors` (always defined — empty `{}` when
there's nothing to report). Repopulate the submitted values with `old()` — see [Session](session.md).

## Form request validation

For request bodies, validate straight into a typed `Schema` and get full editor support on the result:

```python
from arvel import Schema, validate

class CreatePost(Schema):
    title: str
    body: str

post = validate(request.data, CreatePost)  # parsed + type-checked; raises 422 on bad input
```

`Schema` is arvel's typed-data base (a native wrapper over the msgspec engine). For a request object
with `authorize()` and lifecycle hooks, subclass `FormRequest`.

### Injected form requests

Type-hinting a `FormRequest` (or plain `Schema`) as a handler's body param **is** the validation
trigger — the kernel runs the full lifecycle
(`prepare_for_validation` → structural decode → `authorize()` → `rules()` → `passed_validation`)
before your handler body runs, with the same `422`/`403` shapes as `request.validate()`:

```python
async def store(request, payload: CreatePost):   # validated + hooks already run
    ...                                          # payload.slug is set, rules() passed
```

Because the body is decoded **inside** the request pipeline (after every middleware), **auth always
runs first**: a malformed body on a protected route yields `401`/`403`, never a `422` that would leak
the route's shape. The body param can be named anything — it's matched by type, not name.

### Preparing input & after-success hooks

Override `prepare_for_validation` to normalize raw input **before** validation, and
`passed_validation` to derive or clean fields **after** a successful parse:

```python
from arvel import FormRequest

class CreatePost(FormRequest):
    title: str
    slug: str

    @classmethod
    def prepare_for_validation(cls, data):
        # only derive from title if it's actually present and a string — otherwise leave the
        # input untouched so a bad/missing title still fails validation with the normal 422
        title = data.get("title")
        if isinstance(title, str):
            data.setdefault("slug", title.lower().replace(" ", "-"))
        return data

    def passed_validation(self):
        self.title = self.title.strip()
```

### The `rules()` bridge — semantics on top of types

Annotations are the **type/shape** layer (msgspec owns them). When a request needs a check the type
system can't express — a cross-field or conditional rule — override `rules()`, plus the optional
`messages()` / `attributes()` / `with_validator()` hooks:

```python
from arvel.validation import FormRequest, Validator

class Register(FormRequest):
    password: str
    password_confirmation: str

    @classmethod
    def rules(cls) -> dict[str, str | list]:
        return {"password": "confirmed|min:8"}          # runs AFTER msgspec's structural pass

    @classmethod
    def messages(cls) -> dict[str, str]:
        return {"password.confirmed": "Passwords must match."}

    @classmethod
    def attributes(cls) -> dict[str, str]:
        return {"password": "new password"}             # friendly name in messages
```

`rules()` runs against the **decoded** payload once msgspec's structural validation has succeeded; a
failure raises the *same* `ValidationException` (same 422 shape). Types stay in annotations; semantics
go in `rules()`.

!!! note "Structural errors surface before semantic ones"
    `rules()` can only run against a payload msgspec could decode, so a request with *both* a
    structural error (mistyped field) and a semantic one (a `rules()` failure) returns the structural
    error first. Use a plain `Validator` (all-rules-at-once) if you need the single combined bag.

## Manually creating validators

For a request that isn't a typed body, drive the `Validator` yourself. Control how the pass runs:

```python
# bail — stop just THIS field's rules at its first failure (one error, not every failure)
Validator({"x": ""}, {"x": "bail|required|email"}).errors()   # {"x": ["...is required."]}

# stop_on_first_failure — stop the WHOLE pass at the first field to fail
Validator({"a": "", "b": ""}, {"a": "required", "b": "required"},
          stop_on_first_failure=True).errors()                # {"a": [...]} — "b" never checked
```

### After-validation hooks

`after()` adds a post-pass hook for checks no single rule expresses; `add_error()` records the failure:

```python
v = Validator(data, {"starts_at": "date", "ends_at": "date"})
v.after(lambda vv: vv.add_error("ends_at", "must be after starts_at")
        if vv.data["ends_at"] < vv.data["starts_at"] else None)
```

## Working with error messages

Override messages per `rule` or per `field.rule`:

```python
Validator(
    data,
    {"email": "required|email"},
    messages={"email.required": "We need your email to continue."},
)
```

### Localized messages

Without an override, the message resolves through the translator under `validation.<rule>` for the
current locale, falling back to the built-in English defaults (a publishable `validation` lang group
— see [Localization](localization.md)):

```bash
arvel vendor:publish --tag=lang     # writes lang/en/validation.json (+ auth.json, http.json)
```

```jsonc
// lang/es/validation.json — with the locale set to "es", a failing `required` yields this
{ "required": "El campo {field} es obligatorio." }
```

Overrides merge over the defaults **key by key**, so overriding one message keeps the rest.
`{field}` / `{arg}` / `:attribute` placeholders are filled in for you.

### Catching typo'd rules

By default an unrecognized rule name is a silent no-op (forward-compatible) — so `"name": "requried"`
validates nothing. Pass `strict=True` to turn a typo into a loud `UnknownValidationRule` (a
*programmer* error, not a 422); turn it on in development:

```python
Validator(data, {"name": "requried"}, strict=True).passes()   # raises UnknownValidationRule
```

## Available validation rules

| Rule | Checks |
|------|--------|
| `required` | present and non-empty |
| `nullable` / `sometimes` | skip when `None` / skip when the field is absent |
| `string` / `integer` / `numeric` / `boolean` | type |
| `array` / `list` | the value is a list |
| `email` / `url` / `uuid` / `ulid` / `json` / `ip` / `ipv4` / `ipv6` / `mac_address` / `timezone` | format |
| `alpha` / `alpha_num` / `alpha_dash` / `ascii` / `uppercase` / `lowercase` | letters / +digits / +dashes / single-byte / case |
| `min:n` / `max:n` / `size:n` | numbers compare by value; strings/lists by length |
| `between:a,b` / `digits:n` / `digits_between:a,b` / `min_digits:n` / `max_digits:n` | range / exact digits / digit-count bounds |
| `decimal:min[,max]` / `multiple_of:n` | decimal-place count / is a multiple of `n` |
| `gt:f` / `gte:f` / `lt:f` / `lte:f` | compare to another **field** (numeric rule → by value) |
| `in:a,b,c` / `not_in:a,b,c` / `in_array:other.*` | is / isn't one of the listed / exists in another field's array |
| `starts_with:a,b` / `ends_with:a,b` / `doesnt_start_with:a,b` / `doesnt_end_with:a,b` | prefix / suffix (positive and negative) |
| `not_regex:pattern` / `contains:a,b` | doesn't match the pattern / array contains ALL of the listed |
| `confirmed` / `same:f` / `different:f` | matches `<field>_confirmation` / equals / differs from field |
| `regex:/.../` / `accepted` / `accepted_if:f,v` / `declined` / `declined_if:f,v` | matches / yes-on-true (conditionally) / no-on-false (conditionally) |
| `present` / `filled` / `prohibited` / `prohibited_if:f,v` / `prohibited_unless:f,v` | must exist / non-empty-if-present / must be absent-or-empty (conditionally) |
| `required_if:f,v` / `required_unless:f,v` / `required_with(_all):f1,f2` / `required_without(_all):f1,f2` | required depending on another field |
| `exclude` / `exclude_if:f,v` / `exclude_unless:f,v` | drops the field from `validated()` (conditionally) |
| `distinct` | (on a wildcard field `items.*.x`) every sibling value is unique |
| `date` / `date_format:%Y-%m-%d` | parseable date / matches a **Python** strftime format |
| `before:x` / `after:x` / `date_equals:x` | date vs another field or a literal date string |
| `file` / `image` / `mimes:png,jpg` / `mimetypes:image/png` / `extensions:png,jpg` | uploaded file / image / extension |
| `dimensions:min_width=…,max_height=…,ratio=…` | image pixel dimensions (needs the `image` extra — Pillow) |
| `Enum(MyEnum)` (a rule **object**: `{"status": [Enum(Status)]}`) | value is a member of `MyEnum` |

`url` does a structural parse (scheme must be `http`/`https`, non-empty host, no whitespace); `email`
is an RFC-lite regex with length caps. Neither does a DNS or mailbox probe — they're format checks by
design.

## Conditionally adding rules

Apply a rule only when a broader condition holds with `sometimes()`:

```python
v = Validator(data, {})
v.sometimes("card_number", "required", lambda d: d.get("payment_type") == "card")
```

## Validating arrays & nested data

Rule keys are dot-aware: `"user.email": "required|email"` validates the nested value, and
`"items.*.price": "numeric"` validates every element of an array (errors key by index, e.g.
`items.0.price`). `validated()` mirrors that nesting — it returns the validated subset in its
original shape, not flat dotted keys:

```python
data = {"user": {"email": "ada@x.com", "name": "Ada", "note": "x"}, "spam": 1}
Validator(data, {"user.email": "required", "user.name": "required"}).validated()
# -> {"user": {"email": "ada@x.com", "name": "Ada"}}   (only ruled leaves; note/spam dropped)
```

Wildcard rules round-trip the same way: `"items.*.price"` yields `{"items": [{"price": …}, …]}`, each
validated leaf back in its array position.

## Custom validation rules

For logic a string rule can't express, write a `Rule`: a `passes(attribute, value)` predicate plus a
`message`. Drop the instance straight into a field's rule list — it mixes with string rules:

```python
from arvel.validation import Rule

class Uppercase(Rule):
    message = "The :attribute must be uppercase."
    def passes(self, attribute, value) -> bool:
        return isinstance(value, str) and value.isupper()

v = Validator({"code": "abc"}, {"code": ["required", Uppercase()]})
v.errors()                   # {"code": ["The code must be uppercase."]}
```

`:attribute` is replaced with the field name. Custom rules are synchronous predicates, so they run on
both the sync and async paths. For a check that needs the database, use the async string rules
`unique` / `exists` (which require `passes_async` / `validate_async`).

## See also

- [Requests](requests.md) — reading and typing request input.
- [Session](session.md) — flashed `errors` and `old()` input on a redirect-back.
- [Localization](localization.md) — translating validation messages per locale.
