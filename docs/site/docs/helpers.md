# Helpers

Arvel exposes two general-purpose facades for everyday string and array/dict work — `Str` and `Arr`. They're static-method classes that mirror Laravel's `Illuminate\Support\Str` and `Illuminate\Support\Arr`.

```python
from arvel.support import Arr, Str

# or, equivalently:
from arvel import Arr, Str
```

## Str — string facade

### Case conversion

```python
Str.snake("UserProfile")       # "user_profile"
Str.camel("user_profile")      # "userProfile"
Str.kebab("UserProfile")       # "user-profile"
Str.studly("user_profile")     # "UserProfile"
Str.pascal("user_profile")     # "UserProfile" (alias of studly)
```

### Slug and headline

```python
Str.slug("Hello World!")             # "hello-world"
Str.slug("Café déjà vu")             # "cafe-deja-vu"  (diacritics stripped)
Str.slug("Hello World", separator="_")   # "hello_world"

Str.headline("hello_world_greeting") # "Hello World Greeting"
Str.headline("helloWorldGreeting")   # "Hello World Greeting"
```

### Predicates and counts

```python
Str.is_uuid("550e8400-e29b-41d4-a716-446655440000")  # True
Str.word_count("hello world greeting")                # 3
```

### Truncate and pad

```python
Str.limit("a long sentence", 6)              # "a long..."
Str.limit("hi", 6)                            # "hi"
Str.limit("hello world", 5, end="…")         # "hello…"

Str.pad_left("5", 3, "0")                    # "005"
Str.pad_right("5", 3, "0")                   # "500"
Str.pad_both("5", 5, "_")                    # "__5__"
```

### Starts / ends / contains

```python
Str.starts_with("hello world", "hello")           # True
Str.starts_with("hello.png", (".jpg", ".png"))    # False
Str.ends_with("hello.png", (".jpg", ".png"))      # True
Str.contains("hello world", "lo wo")              # True
Str.contains("hello world", ("absent", "world")) # True (any-match)
```

### Slice around a delimiter

```python
Str.after("hello@example.com", "@")     # "example.com"
Str.before("hello@example.com", "@")    # "hello"
Str.after_last("a.b.c", ".")            # "c"
Str.before_last("a.b.c", ".")           # "a.b"
Str.between("foo[bar]baz", "[", "]")    # "bar"
```

### Random strings

```python
Str.random()                         # 16-char URL-safe (letters+digits)
Str.random(40)                       # custom length

Str.password()                       # 32-char with letters/numbers/symbols
Str.password(20, symbols=False)     # only letters and numbers
Str.password(16, letters=False, numbers=True, symbols=False)  # digits only
```

`Str.password` returns the **plaintext**, not a hash. Pass the result through `Hash.make(...)` before storing it.

Both `Str.random` and `Str.password` use `secrets` — cryptographically secure.

## Arr — array / dict facade

### Element access

```python
Arr.first([1, 2, 3])                      # 1
Arr.first([1, 2, 3], lambda x: x > 1)     # 2
Arr.first([], default="missing")          # "missing"

Arr.last([1, 2, 3])                       # 3
Arr.last([1, 2, 3, 4], lambda x: x < 4)   # 3
```

`first` and `last` return the literal first/last element if no predicate is given — falsy values (`0`, `False`, `""`) are **not** treated as missing.

### Reshaping

```python
Arr.flatten([[1, [2, 3]], 4])            # [1, 2, 3, 4]
Arr.flatten([[1, [2, 3]], 4], depth=1)   # [1, [2, 3], 4]

Arr.only({"a": 1, "b": 2, "c": 3}, ["a", "c"])    # {"a": 1, "c": 3}
Arr.except_({"a": 1, "b": 2, "c": 3}, ["b"])      # {"a": 1, "c": 3}

Arr.wrap(None)                            # []
Arr.wrap("hello")                         # ["hello"]
Arr.wrap([1, 2])                          # [1, 2]
```

### Dot notation

```python
Arr.dot({"a": {"b": {"c": 1}}})           # {"a.b.c": 1}
Arr.undot({"a.b.c": 1})                    # {"a": {"b": {"c": 1}}}

Arr.get(payload, "user.profile.email")
Arr.set(payload, "user.profile.email", "alice@example.com")
Arr.has(payload, "user.profile.email")
```

`get` returns the supplied `default` when any segment of the path is missing or a non-mapping. `set` creates intermediate dicts as needed.

### Plucking

```python
Arr.pluck(users, "email")                 # ["a@b.com", "c@d.com", ...]
Arr.pluck(users, "name", key="id")        # {1: "alice", 2: "bob"}
```

`pluck` reads from both dict-shaped items (`item.get(name)`) and object-shaped items (`getattr(item, name, None)`).

### Filtering

```python
Arr.where([1, 2, 3, 4], lambda x: x % 2 == 0)   # [2, 4]
Arr.prepend([2, 3], 1)                          # [1, 2, 3]
```

### Shuffle and divide

```python
Arr.shuffle([1, 2, 3, 4])                 # e.g. [3, 1, 4, 2] — uses secrets.randbelow
keys, values = Arr.divide({"a": 1, "b": 2})
```

`Arr.shuffle` is cryptographically secure. If you need a deterministic, seedable shuffle for tests, drop down to `random.Random(seed).shuffle(list(items))` directly.

## Hashing

For password hashing, use the `Hash` facade — not `Str`:

```python
from arvel.facades import Hash

hashed = Hash.make("secret")             # argon2id by default
ok = Hash.check("secret", hashed)
```

See [Hashing](hashing.md) for parameter tuning and bcrypt fallback.

## URL helpers

```python
from arvel.routing import route

@Route.get("/posts/{id}", name="posts.show")
async def show(id: int) -> ...: ...

route("posts.show", id=42)               # "/posts/42"
```

## Pipeline

`Pipeline` threads a single payload through an ordered sequence of async middleware. Each middleware receives the payload and a `next` callable; it can transform the payload before or after passing it downstream.

```python
from arvel.support import Pipeline

async def log_mw(payload, next):
    print("before:", payload)
    out = await next(payload)
    print("after:", out)
    return out

async def upper_mw(payload, next):
    payload["name"] = payload["name"].upper()
    return await next(payload)

async def handle(payload):
    return payload | {"processed": "true"}

result = await (
    Pipeline()
    .send({"name": "alice"})
    .through([log_mw, upper_mw])
    .then(handle)
)
# → {"name": "ALICE", "processed": "true"}
```

Middlewares run in declaration order (left-to-right). A middleware that doesn't call `next()` short-circuits the chain — useful for guard layers.

The generic signature is `Pipeline[InT, OutT]` — input and output can differ if any middleware transforms the shape.

## Where to next?

- [Collections](collections.md) — chainable list operations.
- [Strings](strings.md) — `Str` reference in detail.
- [Hashing](hashing.md) — password hashing in depth.
