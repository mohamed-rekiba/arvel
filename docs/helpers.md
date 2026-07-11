# Helpers

Every codebase grows a `utils.py` of the same small chores — slugify this string, format that
price, dig a value out of a nested dict, retry a flaky call. arvel ships those so you don't
re-invent them: small, dependency-light utilities for string manipulation, number formatting,
array/dict digging, fluent collections, and control-flow sugar. They're plain functions and
classes — import what you need.

This page covers `Str`, `Number`, `Arr`/`data_get`/`data_set`, `Collection`, and the control-flow
helpers. They're part of the **core** — nothing to install.

## Strings — `Str`

Static one-shots for casing and slugs:

```python
from arvel.support import Str

Str.snake("BlogPost")        # "blog_post"
Str.camel("blog_post")       # "blogPost"
Str.studly("blog_post")      # "BlogPost"
Str.kebab("BlogPost")        # "blog-post"
Str.slug("Hello, World!")    # "hello-world"
Str.random(32)               # a cryptographically-random alphanumeric token
```

(The casing transforms are pure and memoized, so repeated calls on the same input are free.
`Str.random` is the exception — it returns a fresh value every time.)

More `Str` transforms:

```python
Str.title("a nice title")        # "A Nice Title"
Str.headline("create_user")      # "Create User"
Str.plural("category")           # "categories"
Str.singular("categories")       # "category"
Str.upper("ab"); Str.ucfirst("hi")   # "AB" / "Hi"   (also lower / lcfirst)
Str.mask("secret@x.com", "*", 3)     # "sec*********"
```

Length & slicing:

```python
Str.length("abc")                # 3
Str.substr("hello", 1, 3)        # "ell"
Str.take("hello", -2)            # "lo"     (positive counts from the start)
Str.char_at("abc", 1)            # "b"      (None when out of range)
Str.reverse("abc")               # "cba"
Str.repeat("ab", 3)              # "ababab"
Str.words("a b c d", 2)          # "a b..."
Str.word_count("a b c")          # 3
```

Whitespace, padding & affixes:

```python
Str.squish("  a   b  ")          # "a b"
Str.pad_left("5", 3, "0")        # "005"   (also pad_right / pad_both)
Str.start("path", "/")           # "/path" (idempotent — no double slash)
Str.finish("path", "/")          # "path/"
Str.chop_start("/api/x", "/api") # "/x"    (chop_end trims a suffix)
Str.wrap("x", "[", "]")          # "[x]"
```

Search, extract & replace:

```python
Str.between("[abc]", "[", "]")              # "abc"
Str.after("App/Models/User", "/")           # "Models/User"  (after_last → "User")
Str.before("a.b.c", ".")                    # "a"            (before_last → "a.b")
Str.is_("foo/*", "foo/bar/baz")             # True   (only `*` is a wildcard; else literal)
Str.contains_all("foo bar", ["foo", "bar"]) # True
Str.position("hello", "l")                  # 2   (None on miss)
Str.replace_first("a", "X", "banana")       # "bXnana"   (replace_last → "bananX")
Str.replace_array("?", ["1", "2"], "? ?")   # "1 2"
Str.remove("-", "a-b-c")                    # "abc"
Str.swap({"a": "b", "b": "a"}, "ab")        # "ba"   (single pass, like strtr)
```

Predicates & generators:

```python
Str.is_uuid(Str.uuid())          # True   (uuid() generates a v4 UUID)
Str.is_ulid(Str.ulid())          # True
Str.is_json('{"a": 1}')          # True
Str.is_url("https://x.com")      # True
```

### Fluent strings — `Str.of`

Start a fluent `Stringable` with `Str.of`; every transform above has a fluent counterpart that
returns a new `Stringable`, so they chain:

```python
Str.of("  Hello World  ").trim().slug()              # "hello-world"
Str.of("blog_post").studly()                         # "BlogPost"
Str.of("the-quick-brown-fox").title()                # "The Quick Brown Fox"
Str.of("a long sentence ...").limit(10)              # "a long sen..."
Str.of("admin").when(True, lambda s: s.upper())      # conditional → "ADMIN"
Str.of("a,b,c").explode(",").map(str.upper).all()    # ['A', 'B', 'C']  → a Collection
```

`when`/`unless` apply a callback conditionally; `tap` runs a side effect and returns the same
`Stringable`; `pipe` returns whatever its callback returns; `explode` bridges into a `Collection`.
Terminal methods (`length`, `is_json`, `char_at`, `contains_all`, …) return plain values. Call
`.to_str()` (or `str(...)`) to get the plain string back.

## Numbers — `Number`

Locale-aware formatting:

```python
from arvel.support import Number

Number.format(1234567.5)              # "1,234,567.5"
Number.currency(19.99, "USD")         # "$19.99"
Number.percentage(50)                 # "50%"   (takes a 0–100 value)
Number.human(1_500_000)               # "1.5M"
```

`format`/`currency`/`percentage` default to the **active locale** (set by the Locale middleware or
`Lang.set_locale`), so they follow i18n; pass `locale=` to override.

Magnitude, ordinals, sizes & ranges:

```python
Number.abbreviate(1_500_000)          # "1.5M"            (alias of human)
Number.for_humans(1_500_000)          # "1.5 million"     (full words)
Number.ordinal(21)                    # "21st"
Number.file_size(1536, 1)             # "1.5 KB"          (1024-based)
Number.clamp(15, 0, 10)               # 10                (constrain to a range)
Number.trim(12.50)                    # 12.5              (drop trailing zeros)
```

For currency amounts use the dedicated [`Money`](money.md) value object (integer minor units,
penny-perfect `allocate`) rather than `Number` on a `float`.

## Arrays & dicts — `Arr`, `data_get`, `data_set`

```python
from arvel.support import Arr
from arvel.support.helpers import data_get, data_set

Arr.first([1, 2, 3], lambda n: n > 1)         # 2
Arr.pluck(users, "email")                      # ["a@x", "b@x", …]
Arr.flatten([[1, 2], [3, [4]]])                # [1, 2, 3, 4]
Arr.only({"a": 1, "b": 2, "c": 3}, ["a", "c"]) # {"a": 1, "c": 3}

data_get(payload, "user.address.city")         # safe nested read
data_get(order, "items.*.price")               # wildcard → list of prices
data_set(config, "cache.ttl", 600)             # nested write (creates intermediates)
```

`data_get` returns the default (`None`) instead of raising when any segment is missing — ideal
for digging into untrusted JSON. The `*` wildcard collects across a list.

More `Arr` helpers:

```python
Arr.except_({"a": 1, "b": 2}, ["b"])       # {"a": 1}     (alias: excluding)
Arr.add({"a": 1}, "b", 2)                   # {"a": 1, "b": 2}   (set if missing; dot-aware)
Arr.forget({"a": 1, "b": 2}, "b")           # {"a": 1}     (dot-aware, in place)
Arr.pull({"a": 1, "b": 2}, "a")             # 1            (returns it, removes in place; dot-aware)
Arr.has_any({"a": 1}, ["x", "a"])           # True         (any of the dot-keys present)
Arr.where_not_null({"a": 1, "b": None})     # {"a": 1}     (drop None values; keeps keys/order)
Arr.dot({"a": {"b": 1}})                     # {"a.b": 1}   (flatten to dot-keys)
Arr.undot({"a.b": 1})                        # {"a": {"b": 1}}   (expand back)
Arr.collapse([[1, 2], [3]])                  # [1, 2, 3]
Arr.where([1, 2, 3, 4], lambda n: n % 2 == 0)   # [2, 4]
Arr.prepend([2, 3], 1)                       # [1, 2, 3]
Arr.join(["a", "b", "c"], ", ", " and ")     # "a, b and c"   (optional final glue)
Arr.is_assoc({"a": 1})                       # True   (is_list for sequences)
Arr.random([1, 2, 3, 4], 2)                  # 2 distinct picks (secrets-backed)
```

`keys`/`values`/`divide`, `map_with_keys`, `sort`/`sort_desc`, and `take` round out the set.

## Collections — `Collection`

A fluent, chainable wrapper over a list:

```python
from arvel.support import Collection

(Collection([1, 2, 3, 4])
    .filter(lambda n: n % 2 == 0)
    .map(lambda n: n * 10)
    .all())                                     # [20, 40]
```

Beyond `map`/`filter`/`reduce`/`pluck`/`group_by`/`sort`/`sort_by` it carries the everyday
collection surface:

```python
Collection([1, 2, 3, 4]).avg()                          # 2.5   (also max/min/sum/count_by)
Collection([1, 2, 3, 4]).reject(lambda n: n % 2 == 0)   # [1, 3] (inverse of filter)
yes, no = Collection([1, 2, 3, 4]).partition(lambda n: n % 2 == 0)  # ([2,4], [1,3])
Collection([1, 2, 3]).implode("-")                      # "1-2-3" (alias: join)
Collection([1, 2, 3]).pipe(lambda c: c.sum())           # 6
Collection([1, 2, 3]).when(flag, lambda c: c.reverse()) # conditional transform
Collection(records).sort_by_desc("score").pluck("name") # order + project
```

`sum`/`avg` take an optional key **or** callable, the same as `pluck`/`group_by`/`sort_by`:

```python
Collection([{"n": 1}, {"n": 2}]).sum("n")                    # 3
Collection([{"n": 1}, {"n": 2}]).avg(lambda r: r["n"])       # 1.5
Collection([1, 2, 3]).sum()                                  # 6   (no key: sums the items)
```

`zip`/`combine` pair a collection with other iterables:

```python
Collection([1, 2, 3]).zip([4, 5, 6])       # Collection of Collections: [1,4], [2,5], [3,6]
Collection(["a", "b"]).combine([1, 2])     # {"a": 1, "b": 2}   (a plain dict, like key_by/group_by)
```

`duplicates` returns the items that repeat an earlier value, preserving first-seen order — keyed
by **list index**:

```python
Collection([1, 2, 1, 3, 2, 2]).duplicates()          # {2: 1, 4: 2, 5: 2}
Collection(rows).duplicates("email")                 # by key, same shape
```

`when_empty`/`when_not_empty` run a callback only in the matching case (`when` semantics:
the callback's result wins when it returns a `Collection`, otherwise `self` is returned unchanged
— so both are safe to chain):

```python
Collection([]).when_empty(lambda c: log.warning("no rows"))       # runs; still get `self` back
Collection(rows).when_not_empty(lambda c: c.first()).id           # only when non-empty
```

Filter by an item's key/attribute (same `_get` resolution as `pluck`/`group_by`):

```python
users = Collection([{"role": "admin"}, {"role": "user"}, {"role": "guest"}])
users.where_in("role", ["admin", "user"])               # [{admin}, {user}]
users.where_not_in("role", ["admin"])                   # [{user}, {guest}]
Collection(rows).where_not_null("deleted_at")           # rows with a value (where_null for None/missing)
Collection([1, 2, 3, 4, 5]).take(2)                     # [1, 2]  (take(-2) → [4, 5])
```

`reverse`/`skip`/`slice`/`nth`/`take`, `where`/`where_in`/`where_not_in`/`where_null`/`where_not_null`,
`merge`/`concat`/`flat_map`, `search`/`value`/`every`, and `tap` round out the set — all returning a
new `Collection` (or a plain value for terminals).

**No higher-order proxy.** Some collection libraries offer a magic `collection.map.name` shorthand
that implicitly maps over an attribute. arvel intentionally **doesn't**: a dynamic `__getattr__`
proxy can't be typed — every call through it would collapse to `Any`, which conflicts with arvel's
strict-typing mandate. The idiomatic Python replacement is a lambda, and it types end-to-end:

```python
Collection(users).map(lambda u: u.name)         # typed: Collection[str], not Any
Collection(users).each(lambda u: u.activate())
```

For large or streaming sources, `lazy()` gives a **deferred** view — `map`/`filter`/`take`
don't run until you materialize, and only as many elements as you consume are produced:

```python
from arvel.support import LazyCollection

(Collection(huge_list).lazy()
    .map(expensive)            # nothing runs yet
    .filter(is_valid)
    .take(10)                  # stops after 10 — the rest is never touched
    .to_list())
```

## Control-flow sugar

```python
from arvel.support import optional
from arvel.support.helpers import tap, pipe, blank, filled, throw_if, throw_unless, rescue, retry

tap(user, lambda u: log.info("created", id=u.id))   # run a side effect, return user
pipe(value, transform_a, transform_b)               # value |> a |> b

blank("")       # True   (None, "", [], {} are "blank")
filled("x")     # True

throw_if(not user.is_admin, Forbidden())            # raise when the condition holds
throw_unless(user.is_admin, Forbidden())            # raise when the condition is falsy

optional(maybe_user).name                           # None if maybe_user is None, else .name
optional(maybe_dict)["key"]                         # null-safe item access too

rescue(lambda: risky(), default=0)                  # swallow exceptions, return default
retry(3, lambda: flaky_call(), sleep=0.5)           # retry up to 3× with a delay
```

## Global functions

Lowercase shorthands for the chores you reach for constantly — importable straight off `arvel`.
Most are one-liners over a facade or the current request; they exist so call sites stay short.

**Debug** — dump a value (or several) while you're chasing something down:

```python
from arvel import dump, dd

dump(payload)              # pretty-print (rich if installed, else pprint) and RETURN it
x = dump(compute())        # drops into an expression — returns its single argument
dd(request(), payload)     # "dump and die" — print, then stop the current unit of work
```

`dd` is context-aware: inside the interactive `shell` (tinker) it dumps and returns, so your
session continues; everywhere else it raises `DumpDie`, which the request pipeline renders as a
debug response (ending that request) and the CLI turns into a clean non-zero exit. Models print
their stored columns — `User(id=1, email='a@b.com')`.

**Filesystem paths** — resolved against the application root (honouring `with_config_dir` /
`with_lang_dir` overrides):

```python
from arvel import base_path, storage_path, config_path, database_path

base_path("routes/web.py")     # "<root>/routes/web.py"
storage_path("logs/app.log")   # "<root>/storage/logs/app.log"
config_path()                  # the config dir (override, else "<root>/config")
database_path("seeders")       # "<root>/database/seeders"
```

(`app_path`, `public_path`, `resource_path`, `lang_path` complete the set — each joins its
segment onto the root.)

**Guards & error reporting** — the conditional siblings of `abort` and the exception handler:

```python
from arvel import abort_if, abort_unless, report, report_if

abort_if(order.locked, 409, "Order is locked")     # raise the HTTP status when truthy
abort_unless(user.can_edit, 403)                    # …when falsy
report(caught_exception)                            # log to the bound handler WITHOUT raising
report_if(rows_dropped, DataLoss(...))              # report only when the condition holds
```

**Value piping** — run a callback only when there's a value:

```python
from arvel import transform

transform(request().get("name"), str.upper)              # None input → None
transform(maybe, expensive, default="n/a")               # blank/None → the default
```

**Shorthands over facades & the container:**

```python
from arvel import collect, resolve, event, info, bcrypt, encrypt, decrypt, validator, policy

collect([1, 2, 3]).map(...)          # wrap in a Collection
resolve(MailManager)                 # container resolve — alias of app(MailManager)
event(OrderShipped(order))           # dispatch through the event bus
info("order.paid", id=order.id)      # info-level log line
digest = bcrypt(password)            # hash with the default hasher
token = encrypt({"uid": 7}); decrypt(token)      # round-trip via the app key
validator(data, {"email": "required|email"})     # build a validator
```

`info(...)` / `logger()` are structured-logging entry points: the **first argument is the event
name** (rendered as a string), and everything else is **keyword context** (structured fields). So
pass an object as context, not as the event — and hand the logger something serializable, since a
raw model logs as its `repr`, not as fields:

```python
user = await User.first()

logger().info(user)                       # ⚠ the model becomes the event STRING (its repr)
                                          #   {"event": "User(id=1, name='Super Admin', …)", …}

logger().info("user.loaded", user=user.to_dict())   # ✓ structured — fields under `user`
info("user.loaded", user=user.to_dict())            # same, via the info() shorthand
# {"event": "user.loaded", "user": {"id": 1, "name": "Super Admin", …}, "level": "info", …}
```

(JSON vs the pretty console format is a separate switch — the renderer is JSON only when
`app.env == "production"`, pretty key=value otherwise.)

**Current-request accessors** — read the in-flight request; safe (return `None`/the default)
when called outside a request cycle:

```python
from arvel import request, session, cookie, old

request()                    # the Request, or None off-cycle
session()                    # the session dict (web group), or None
cookie("sid", default=None)  # a cookie value
old("email")                 # flashed old input after a redirect-back
```

**Small utilities** — `class_basename(obj)` (the class name without its module), `enum_value(x)`
(a member's `.value`, else `x` unchanged), `literal(name="x", n=1)` (an ad-hoc object with named
attributes), `noop` (a callable that accepts anything and does nothing), `windows_os()`.

## Common mistakes & gotchas

- **Treating `Stringable` as a `str`.** It isn't one — it wraps a string. Call `.to_str()` (or
  `str(...)`) before passing it where a real `str` is required.
- **`data_get` swallowing typos.** A missing path returns the default silently; if a key
  *should* exist, that quietness can hide a bug — pass a sentinel default to tell "missing"
  apart from a real `None`.
- **`blank` vs falsy.** `blank(0)` is `False` and `blank("0")` is `False` — `blank` means
  "empty," not "falsy." Use it when an empty string/list should count as absent.

## How it works

These are leaf utilities — they depend only on light libraries (inflection, slugify, ulid,
Babel for number locales) and nothing else in arvel, so they import cheaply and are safe to use
anywhere, including inside the light core. `Str.of` and `Collection` are thin fluent wrappers;
the static helpers are pure functions.

## See also

- [Validation](validation.md) — `data_get`'s wildcard powers `items.*.field` rules.
- [Database & ORM](database/index.md) — `Collection` wraps query results.
