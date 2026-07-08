# Localization

Hardcoded English strings are a wall between your app and everyone who doesn't read English — and
"1 item" vs "2 items" isn't a simple `if`, since plural rules differ wildly by language (Polish has
three forms, Arabic six). arvel handles both: it translates your strings from per-locale files and
picks the right plural form per language. The core does key lookup, placeholder replacement, and
simple pluralization with **no extra dependency**; add `[i18n]` and **Babel** powers correct CLDR
plural rules for every language.

This page covers organizing translation files, translating strings, pluralization, and setting the
active locale per request.

!!! note "Needs the `[i18n]` extra for CLDR plurals"
    Key lookup, placeholder replacement, and a simple one/other plural split are **core** — nothing to
    install. Correct CLDR plural rules for every language (Polish's `few`/`many`, Arabic's six forms)
    need Babel: `uv add 'arvel[i18n]'`.

## Translation files

Put translations under a `lang/` directory, one file per locale (JSON or grouped):

```jsonc
// lang/en.json
{ "welcome": "Welcome, :name", "messages": { "saved": "Saved!" } }

// lang/fr.json
{ "welcome": "Bienvenue, :name", "messages": { "saved": "Enregistré !" } }
```

The app's `lang/` directory is loaded automatically at boot, so `lang/<code>.json` and
`lang/<code>/<group>.json` files are available through `trans`/`__` with no wiring.

Prefer a different location (e.g. `resources/lang`)?
`with_lang_dir(...)` overrides the default:

```python
Application.configure(base_path=".").with_lang_dir("resources/lang").create()
```

`vendor:publish --tag=lang` (below) also respects this override — it publishes into whichever
directory is actually configured, not always `lang/`.

## Default messages & publishing

arvel ships default translations for its own framework messages — `validation`, `auth`, and `http`
— under the `en` locale, loaded automatically. So every framework-emitted message is
localized: validation errors, and the auth/HTTP responses (`auth.unverified`,
`auth.already_authenticated`, `http.csrf`, `http.too_many_requests`, `http.not_found`, …) all run
through `trans()` and follow the active locale. Even the generic HTTP status texts that `abort(404)`
and the error renderer fall back to are localizable under `http.status` — `http.status.404`
("Not Found"), `http.status.419` ("Page Expired"), `http.status.500`, … Translate any of these
by adding the same groups under other locales (`lang/fr/http.json` with `{"status": {"404": "Introuvable"}}`,
`lang/fr/auth.json`, …).

To customize them, publish the defaults into your app and edit the copies:

```bash
arvel vendor:publish --tag=lang     # copies the framework defaults into your lang dir's en/
```

This writes `en/validation.json`, `auth.json`, and `http.json` under `lang/` (or your
`with_lang_dir(...)` override). Your app's translations **override**
the framework defaults **key by key** (a one-level-deep merge), so you can change a single message
without re-declaring the rest:

```jsonc
// lang/en/validation.json — override just one rule; the other defaults still apply
{ "required": "Please provide a value for {field}." }
```

Add other locales the same way — `lang/fr/validation.json`, etc. — and they layer over the `en`
fallback. (Translating `validation.*` is how you localize validation error messages; see
[Validation](validation.md).)

## Translating

`trans` (alias `__`) looks up a dotted key and fills `:placeholder` tokens:

```python
from arvel.localization import trans, __

trans("welcome", name="Ada")            # "Welcome, Ada"
__("messages.saved")                     # "Saved!"
```

Case-follows-the-token: `:name` → `Ada`, `:Name` → `Ada` (ucfirst), `:NAME` → `ADA`. Replacement is
longest-key-first, so `:name` never eats a longer `:name_full` token when both are supplied.

In templates the same functions are globals:

```html
<h1>{{ trans("welcome", name=user.name) }}</h1>
```

If a key is missing in the active locale, the key itself is returned — so a missing translation
is visible, not a crash.

## Pluralization

`trans_choice` selects a form based on a count. Define the forms pipe-separated (singular first,
then the plural/other form), and `:count` interpolates the number:

```json
{ "apples": "one apple|:count apples" }
```

```python
from arvel.localization import trans_choice

trans_choice("apples", 1)     # "one apple"
trans_choice("apples", 5)     # "5 apples"
trans_choice("apples", 0)     # "0 apples"   (0 takes the "other" form)
```

For explicit control, prefix a segment with an exact count `{n}` or an interval `[low,high]`
(`*` is open-ended). A matching selector wins; segments without one fall back to the plural category:

```json
{ "apples": "{0} no apples|{1} one apple|[2,*] :count apples" }
```

```python
trans_choice("apples", 0)     # "no apples"
trans_choice("apples", 7)     # "7 apples"      ([2,*] matched)
```

The core pipe form covers the common one/other split. With `[i18n]` installed, Babel supplies
the full **CLDR** categories (`zero`/`one`/`two`/`few`/`many`/`other`) — essential for languages
like Polish, Russian, or Arabic where "few" and "many" differ:

```python
plural_category("pl", 2)     # "few"   (Babel CLDR)
plural_category("pl", 5)     # "many"
```

## The active locale

The current locale lives in a context variable, so it's **isolated per request / per async
task** — concurrent requests in different languages don't bleed into each other:

```python
from arvel.localization import current_locale

current_locale.set("fr")
trans("messages.saved")        # "Enregistré !"
```

`LocaleMiddleware` sets it from the request's `Accept-Language` header for the duration of each
request and resets it afterward, so you rarely set it by hand.

## Translatable model attributes

Beyond UI strings, **content** is often multilingual (a product name in en/fr/de). Mix in
`HasTranslations` and cast an attribute as `Translatable` — it's stored as a JSON object
`{locale: value}` (back it with a `jsonb` column) and **read as the current locale's value**:

```python
from arvel.localization import HasTranslations, Translatable

class Product(HasTranslations, Model):
    __casts__ = {"name": Translatable(), "description": Translatable()}

product.name = {"en": "Phone", "fr": "Téléphone"}   # set the whole map…
product.set_translation("name", "de", "Telefon")     # …or one locale at a time
current_locale.set("fr"); product.name                # "Téléphone"  (falls back to the default locale)
```

Index a specific locale you filter/sort by with a B-tree expression index —
`t.btree_index("name->>'en'")` (GIN is for containment search; see
[JSON, Full-text & Vectors](database/json-search.md)).

## Common mistakes & gotchas

- **Setting the locale globally.** Don't reach for a module global — the context variable is
  what keeps concurrent requests isolated. Set it via the middleware or `current_locale.set`
  within the request scope.
- **Expecting CLDR plurals without `[i18n]`.** The core fallback is a simple one/other split;
  languages with `few`/`many` need Babel. Install the `[i18n]` extra.
- **Wrong placeholder token.** Replacement is `:name` (and `{name}`), not `%name%` — match the
  token your files use.
- **Ambiguous locale resolution.** A locale switches by URL prefix, `Accept-Language`, or a
  stored user preference — whichever your middleware checks first wins. Be explicit about that
  order so it's predictable.

## How it works

A `Translator` holds per-locale dictionaries loaded from `lang/`. `trans` resolves a dotted key
against the active locale (falling back to the key), then substitutes placeholders.
`trans_choice` first picks the plural category — Babel's CLDR rule when `[i18n]` is present,
else the pipe fallback — then formats the chosen segment. The active locale is a `ContextVar`,
which is why concurrency-safe per-request localization works without passing the locale around.

## See also

- [Validation](validation.md) · [Mail](mail.md) — both honor the active locale.
- [Dates & Time](dates.md) — locale-aware formatting.
- [Views](views.md) — `trans`/`trans_choice` are template globals.
