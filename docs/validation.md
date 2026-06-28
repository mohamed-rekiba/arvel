# Validation

Never trust what arrives over the wire. Before a request body reaches your business logic, you want
to know it's shaped the way you expect — required fields present, an email that's actually an email,
an age that's a number in range. arvel gives you two complementary ways to enforce that: a rule-based
**`Validator`** for quick, dynamic checks (rules as `|`-delimited strings), and typed **`Schema`** /
**`FormRequest`** objects when you want the validated data to come back fully typed. Either way, bad
input becomes a clean `422` your app renders for the right client automatically.

This page covers both, plus custom rules, custom and localized messages, and how errors reach a
browser form versus an API. Validation is part of the **core** — no extra to install.

## The Validator

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

`passes()` / `fails()` return booleans. `errors()` returns a `dict[str, list[str]]` keyed by
field. `validated()` returns just the fields that had rules.

You can also build one through the [`Validator` facade](facades.md), which reads naturally and is
swappable in tests:

```python
from arvel import Validator

validator = Validator.make(request.data, {"email": "required|email"})
```

## Validate-or-raise

`validate()` returns the validated data, or raises a `422` `ValidationException` carrying the
error dict — let arvel's exception handler turn it into a response:

```python
clean = Validator(request.data, {"email": "required|email"}).validate()
```

## How errors are rendered (content negotiation)

A raised `ValidationException` is rendered by the framework's exception handler to match the
client — you write `validate()` once and the right response comes out:

| Client | Signal | Response |
|--------|--------|----------|
| API / SPA | `Accept: application/json` (or no `Accept`) | `422` with `{"message": ..., "errors": {...}}` |
| Inertia | `X-Inertia: true` | `422` with the same `{message, errors}` body |
| Browser | `Accept: text/html` | **redirect back** (`302`) to the `Referer`, with the errors flashed to the session **error bag** |

So an API gets machine-readable per-field errors, while a browser is sent back to the form with
`$errors` available to the template on the next request:

```python
# in a Jinja template, after a redirect-back:
{% if errors %}<ul>{% for field, msgs in errors.items() %}<li>{{ msgs[0] }}</li>{% endfor %}</ul>{% endif %}
```

The `errors` variable is put there for you: the **web** middleware group runs
`ShareErrorsFromSession`, which reads the flashed error bag from the session on every request and
shares it with the view as `errors` (so it's always defined — empty `{}` when there's nothing to
report). It's the same bag the redirect-back response writes — the session flash bag.

## Custom rule objects

For logic a string rule can't express, write a `Rule`: an async `passes(attribute, value)` plus a
`message`. Drop the instance straight into a field's rule list — it mixes with string rules:

```python
from arvel.validation import Rule

class Uppercase(Rule):
    message = "The :attribute must be uppercase."
    async def passes(self, attribute, value) -> bool:
        return isinstance(value, str) and value.isupper()

v = Validator({"code": "abc"}, {"code": ["required", Uppercase()]})
await v.fails_async()        # True
v.errors()                   # {"code": ["The code must be uppercase."]}
```

`:attribute` in the message is replaced with the field name. Custom rules run on the **async** path
(`passes_async` / `validate_async`), alongside the DB rules `unique` / `exists`.

## Available rules

| Rule | Checks |
|------|--------|
| `required` | present and non-empty |
| `nullable` / `sometimes` | skip when `None` / skip when the field is absent |
| `string` / `integer` / `numeric` / `boolean` | type |
| `array` | the value is a list |
| `email` / `url` / `uuid` / `json` / `ip` | format |
| `alpha` / `alpha_num` / `alpha_dash` | letters / +digits / +dashes & underscores |
| `min:n` / `max:n` / `size:n` | numbers compare by value; strings/lists by length |
| `between:a,b` / `digits:n` / `digits_between:a,b` | range / exact digits / digit-count range |
| `gt:f` / `gte:f` / `lt:f` / `lte:f` | compare to another **field** (numeric rule → by value) |
| `in:a,b,c` / `not_in:a,b,c` | is / isn't one of the listed values |
| `starts_with:a,b` / `ends_with:a,b` | prefix / suffix is one of the listed |
| `confirmed` / `same:f` / `different:f` | matches `<field>_confirmation` / equals / differs from field |
| `regex:/.../` / `accepted` | matches the pattern / is yes/on/1/true |
| `date` / `date_format:%Y-%m-%d` | parseable date / matches a **Python** strftime format |
| `before:x` / `after:x` / `date_equals:x` | date vs another field or a literal date string |
| `file` / `image` / `mimes:png,jpg` | uploaded file / image / allowed extension |

Rule keys are dot-aware: `"user.email": "required|email"` validates the nested value, and
`"items.*.price": "numeric"` validates every element of an array (errors key by index, e.g.
`items.0.price`).

`validated()` mirrors that nesting — it returns the validated subset with its original shape, not
flat dotted keys:

```python
data = {"user": {"email": "ada@x.com", "name": "Ada", "note": "x"}, "spam": 1}
Validator(data, {"user.email": "required", "user.name": "required"}).validated()
# -> {"user": {"email": "ada@x.com", "name": "Ada"}}   (only ruled leaves; `note`/`spam` dropped)
```

Wildcard rules round-trip the same way: `"items.*.price"` yields `{"items": [{"price": …}, …]}`,
each validated leaf back in its array position. (Numeric path segments are always array indices, and
a list may contain `None` holes where a ruled leaf was absent from some elements — so positions stay
aligned.)

## Strict mode — catch typo'd rules

By default an unrecognized rule name is a silent no-op (forward-compatible). That means a typo passes
quietly — `"name": "requried"` validates *nothing*. Pass `strict=True` to turn that into a loud
error:

```python
Validator(data, {"name": "requried"}).passes()              # True — typo silently ignored
Validator(data, {"name": "requried"}, strict=True).passes() # raises UnknownValidationRule('requried')
```

`UnknownValidationRule` is a **programmer** error, not a user-input failure — it is *not* a
`ValidationException` and does not render as 422. Turn it on in development to surface misspelled or
unsupported rules early. (`unique` / `exists` and custom `Rule` objects are recognized and never
flagged, even though they're validated on the async path.)

## Custom messages

Override messages per `rule` or per `field.rule`:

```python
Validator(
    data,
    {"email": "required|email"},
    messages={"email.required": "We need your email to continue."},
)
```

### Localized messages

Without an override, the message resolves through the translator under `validation.<rule>` for
the **current locale**, falling back to the framework's built-in English defaults (which ship as a
publishable `validation` lang group — see [Localization](localization.md)).

To customize the defaults, publish them and edit the copies; to translate, add a `validation` group
per locale under `lang/`:

```bash
arvel vendor:publish --tag=lang     # writes lang/en/validation.json (+ auth.json, http.json)
```

```json
// lang/es/validation.json — with the locale set to "es", a failing `required` yields this
{ "required": "El campo {field} es obligatorio." }
```

Your `lang/` overrides merge over the framework defaults **key by key**, so overriding one message
keeps the rest.

`{field}` (and `{arg}` / `:attribute`) placeholders are filled in for you.

## Typed form objects

For request bodies, validate straight into a typed `Schema` and get full editor support on the
result:

```python
from arvel import Schema, validate

class CreatePost(Schema):
    title: str
    body: str

post = validate(request.data, CreatePost)  # parsed + type-checked; raises 422 on bad input
```

`Schema` is arvel's typed-data base (a native wrapper over the msgspec engine) — you subclass it
rather than importing `msgspec` yourself. For a request object with `authorize()`, subclass
`FormRequest` instead.

### FormRequest lifecycle hooks

A `FormRequest` exposes two hooks around the parse. Override `prepare_for_validation` to normalize
raw input **before** validation, and `passed_validation` to derive or clean fields **after** a
successful parse:

```python
from arvel import FormRequest

class CreatePost(FormRequest):
    title: str
    slug: str

    @classmethod
    def prepare_for_validation(cls, data):
        data.setdefault("slug", data["title"].lower().replace(" ", "-"))  # default the slug
        return data

    def passed_validation(self):
        self.title = self.title.strip()                                   # tidy after success

post = CreatePost.parse({"title": "Hello World"})   # → slug "hello-world", title trimmed
```

> A `with_validator()`-style hook has no place here on purpose: that pattern drives the **rule**
> engine, so it lives on [`Validator`](#the-validator) (use a custom `Rule` or an `after` step),
> while `FormRequest` stays type-driven. Pick the rule `Validator` when you need conditional rules;
> pick `FormRequest` when you want a typed object.

## Common mistakes & gotchas

- **Forgetting `nullable` before a type rule.** `"age": "integer|min:18"` rejects a missing value;
  `"age": "nullable|integer|min:18"` skips the rest when it's `None`. Order matters — `nullable`
  goes first.
- **DB rules need the async path.** `unique` / `exists` and custom `Rule` objects run on
  `passes_async` / `fails_async` / `validate_async`. The sync `passes()` / `validate()` only run the
  string rules — call the async variants when a rule touches the database.
- **`min`/`max` mean different things by type.** On a number they compare the **value**; on a string
  or list they compare the **length**. `"name": "max:255"` caps length; `"age": "max:120"` caps the
  number.
- **Expecting `validated()` to include un-ruled fields.** It returns only the fields that had rules —
  a deliberate allow-list, so stray keys never leak through.

## How it works

The `Validator` walks each field's rules in order, short-circuiting on `nullable`, and collects
per-field messages into an `errors()` map (resolved through the [translator](localization.md) for
the current locale). `validate()` raises a `ValidationException` carrying that map, which the
framework's exception handler renders by content negotiation. The typed path is different: `Schema`
/ `FormRequest` parse straight into a msgspec struct, so validation *is* the type-check — you get a
fully-typed object back or a `422`.

## See also

- [Routing](routing.md) — where request handlers receive and validate input.
- [Localization](localization.md) — translating validation messages per locale.
- [Middleware](middleware.md) — `ShareErrorsFromSession`, which puts `errors` in your views.
