# Localization

<a name="introduction"></a>
## Introduction

Arvel's localization features provide a convenient way to retrieve strings in various languages, letting you support multiple languages in your application. Translation strings are loaded from Python or JSON files; the active locale is negotiated per request by `SetLocaleMiddleware` once you mount it (it isn't applied automatically).

The `LangServiceProvider` is **auto-registered** — it binds the `Translator` and wires up the translation helpers.

<a name="defining-translation-strings"></a>
## Defining Translation Strings

Translation strings live in language files keyed by locale. Arvel ships two loaders: a Python loader and a JSON loader. A JSON catalog looks like this:

```json
{
    "welcome": "Welcome to our application",
    "messages.greeting": "Hello, :name"
}
```

<a name="retrieving-translation-strings"></a>
## Retrieving Translation Strings

Use the `__` helper to look up a key. If no translation is bound (or the key is missing), it returns the key unchanged:

```python
from arvel.i18n.helpers import __

__("welcome")
```

<a name="replacing-parameters"></a>
### Replacing Parameters

Define placeholders with a leading colon and pass keyword replacements:

```python
__("messages.greeting", name="Ada")
# "Hello, Ada"
```

The `locale` argument is keyword-only, so it can never collide with a placeholder named `locale`. Pass it to override the default locale for one call:

```python
__("welcome", locale="es")
```

<a name="pluralization"></a>
### Pluralization

`__choice` selects the correct plural form for a count, using Laravel-style pipe/bracket syntax in the translation string:

```python
from arvel.i18n.helpers import __choice

__choice("messages.apples", count=1)   # "1 apple"
__choice("messages.apples", count=5)   # "5 apples"
```

<a name="per-request-locale"></a>
## Per-Request Locale

`SetLocaleMiddleware` negotiates the locale for each request and stores it on `request.state.locale`. It's not auto-mounted — register it on your app to enable per-request locale. The request-aware `t` helper reads that locale automatically, so handlers get the right language without threading it through manually:

```python
from starlette.requests import Request
from arvel.i18n.helpers import t


async def greet(request: Request) -> dict[str, str]:
    return {"message": t(request, "messages.greeting", name="Ada")}
```

> [!NOTE]
> `t` is concurrency-safe — it passes the per-request locale to `__` rather than mutating the shared `Translator`. When the middleware hasn't run, it falls back to `"en"`.
