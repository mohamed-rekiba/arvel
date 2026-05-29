# Strings

The `Str` facade in `arvel.support` mirrors Laravel's `Illuminate\Support\Str`. Every entry is a `@staticmethod` so call sites stay terse.

```python
from arvel.support import Str
# or: from arvel import Str
```

For the array/dict equivalent, see [Arr](helpers.md#arr-array-dict-facade).

## Case conversion

```python
Str.snake("UserProfile")        # "user_profile"
Str.camel("user_profile")       # "userProfile"
Str.kebab("UserProfile")        # "user-profile"
Str.studly("user_profile")      # "UserProfile"  (alias: Str.pascal)
```

The converters accept any of `PascalCase`, `camelCase`, `snake_case`, `kebab-case`, or space-separated input.

## Slug and headline

```python
Str.slug("Hello World!")                 # "hello-world"
Str.slug("Café déjà vu")                 # "cafe-deja-vu"      (diacritics stripped)
Str.slug("Hello World", separator="_")  # "hello_world"

Str.headline("hello_world_greeting")    # "Hello World Greeting"
Str.headline("helloWorldGreeting")      # "Hello World Greeting"
```

## Predicates

```python
Str.is_uuid("550e8400-e29b-41d4-a716-446655440000")   # True
Str.is_uuid("not-a-uuid")                              # False
```

## Word count

```python
Str.word_count("hello world greeting")   # 3
Str.word_count("  spaced   out  ")       # 2
```

## Truncate and pad

```python
Str.limit("a long sentence", 6)           # "a long..."
Str.limit("a long sentence", 6, end="…")  # "a long…"
Str.limit("short", 10)                    # "short"     (no change)

Str.pad_left("5", 3, "0")                 # "005"
Str.pad_right("5", 3, "0")                # "500"
Str.pad_both("5", 5, "_")                 # "__5__"
```

## Starts / ends / contains

```python
Str.starts_with("hello world", "hello")          # True
Str.starts_with("hello.png", (".jpg", ".png"))   # False  (matches prefix, not extension)
Str.ends_with("hello.png", (".jpg", ".png"))     # True

Str.contains("hello world", "lo wo")              # True
Str.contains("hello world", ("missing", "world"))  # True  (any match)
```

`needles` can be a string or a tuple of strings.

## Slicing around delimiters

```python
Str.after("hello@example.com", "@")        # "example.com"
Str.before("hello@example.com", "@")       # "hello"

Str.after_last("a.b.c", ".")               # "c"
Str.before_last("a.b.c", ".")              # "a.b"

Str.between("foo[bar]baz", "[", "]")       # "bar"
```

If the delimiter isn't found, `after` / `before` return the full string unchanged.

## Random and password generation

Both use `secrets` — never `random` — and are safe for tokens, API keys, and one-time passwords.

```python
Str.random()           # 16-char URL-safe (ASCII letters + digits)
Str.random(40)         # custom length

Str.password()         # 32-char, letters + numbers + symbols
Str.password(20, symbols=False, spaces=False)
Str.password(16, letters=False, numbers=True, symbols=False)  # digits only
```

`Str.password` returns plaintext — pass it through `Hash.make(...)` if you're storing it.

## Type coercion

These helpers parse strings into typed values and raise `ValueError` on bad input. They're useful for env var parsing and any place you receive string data and need a typed result.

```python
Str.to_bool("yes")      # True
Str.to_bool("off")      # False
Str.to_bool(" True ")   # True   (whitespace stripped, case-insensitive)
# Accepted truthy:  "true", "1", "yes", "y", "on"
# Accepted falsy:   "false", "0", "no", "n", "off"
# Raises ValueError for anything else (including None or empty string)

Str.to_int("42")        # 42
Str.to_float("3.14")    # 3.14
# Both raise ValueError with a descriptive message on invalid input

Str.to_list("a, b, c")                              # ["a", "b", "c"]
Str.to_list("a| b ", separator="|", strip_items=False)  # ["a", " b"]
Str.to_list("a,,b", remove_empty=True)              # ["a", "b"]

Str.to_dict("key=val,foo=bar")                      # {"key": "val", "foo": "bar"}
Str.to_dict("a:1;b:2", item_separator=";", key_value_separator=":")
# {"a": "1", "b": "2"}
```

## See also

- [Helpers](helpers.md) — broader facade catalogue, including `Arr`.
- [Collections](collections.md) — fluent chaining over lists.
- [Hashing](hashing.md) — password hashing in depth.
