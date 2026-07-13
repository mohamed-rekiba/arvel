# Strings

arvel provides `Str`, a collection of string-manipulation functions, and a fluent `Stringable` wrapper
for chaining them. Most helpers exist because Python's `str` lacks the higher-level, framework-flavored
operations (case conversion, inflection, slugs) you reach for constantly in a web app.

## Introduction

There are two styles. `Str` is a set of static methods for one-off transformations; `Str.of()` returns
a `Stringable` you can chain fluently and unwrap at the end.

```python
from arvel.support import Str

Str.slug("Arvel Framework")        # "arvel-framework"
Str.of("  Hello  ").trim().lower().slug()   # a chainable Stringable
```

## Available methods

### Case & inflection

```python
Str.camel("foo_bar")        # "fooBar"
Str.studly("foo_bar")       # "FooBar"
Str.snake("fooBar")         # "foo_bar"
Str.kebab("fooBar")         # "foo-bar"
Str.title("a nice day")     # "A Nice Day"
Str.headline("some_method") # "Some Method"
Str.plural("post")          # "posts"
Str.singular("posts")       # "post"
```

### Slugs & identifiers

```python
Str.slug("Hello World!", separator="-")   # "hello-world"
Str.ulid()                                # a sortable unique id
Str.is_uuid(value)                        # True for a well-formed UUID
```

### Search & extraction

```python
Str.contains("haystack", "st")     # True
Str.starts_with("arvel", "arv")    # True
Str.ends_with("arvel", "vel")      # True
Str.after("a@b.com", "@")          # "b.com"
Str.before("a@b.com", "@")         # "a"
Str.after_last("a/b/c", "/")       # "c"
Str.before_last("a/b/c", "/")      # "a/b"
Str.is_("admin/*", "admin/users")  # glob match → True
```

### Trimming & masking

```python
Str.limit("A long sentence", 6)     # "A long..."
Str.mask("4242424242424242", "*", index=0, length=12)   # "************4242"
```

## Fluent strings

`Str.of()` wraps a value so every operation returns another `Stringable`, letting you chain — then
`.to_str()` (or `str()`) unwraps:

```python
name = (
    Str.of("  Jane DOE  ")
       .trim()
       .title()          # "Jane Doe"
       .slug()           # "jane-doe"
       .to_str()
)
```

`Stringable` exposes the full toolbox — case (`upper`/`lower`/`ucfirst`/`camel`/`snake`/`slug`…),
extraction (`after`/`before`/`between`/`substr`/`take`), editing (`replace`/`replace_first`/`remove`/
`swap`/`mask`), inflection (`plural`/`singular`/`headline`), and trimming (`limit`/`words`/`excerpt`/
`word_wrap`) — each returning a new `Stringable` so nothing mutates in place.

## See also

- [Helpers](helpers.md) — other general-purpose helpers (arrays, numbers, URLs).
- [Collections](collections.md) — the same fluent style over lists.
