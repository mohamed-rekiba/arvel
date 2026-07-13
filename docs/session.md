# Session

HTTP is stateless, yet most apps need to remember something about a user across requests — a signed-in
identity, a "post created" notice, the values the user just typed into a form that failed validation.
arvel provides a session store for exactly this, plus a **flash** layer for data that should survive
one redirect and then disappear.

## Introduction

The session is a per-visitor dictionary persisted between requests. It is started by the `StartSession`
middleware (wired into the `web` group), which reads the session cookie on the way in and writes it
back on the way out. Anywhere in a request you reach the session dict with the `session()` helper, and
its one-request **flash** layer with `FlashBag`.

## Configuration

The session is configured in `config/session.py`:

```python
# config/session.py
config = {
    "driver": "cookie",          # "cookie" (signed, self-contained) or "redis" (server-side)
    "lifetime": 120,             # minutes of inactivity before the session expires
    "cookie": "arvel_session",   # the cookie name
    "secure": True,              # only send over HTTPS
}
```

The default **cookie** driver stores the (signed, tamper-evident) session in the client cookie — no
server-side store to provision. Switch `driver` to `"redis"` when the session outgrows a cookie or you
need server-side revocation; see [Cache](cache.md) for the connection.

## Interacting with the session

The `session()` helper returns the current request's session dict (or `None` outside a request):

```python
from arvel.http import session

sess = session()
sess["user_id"]                 # read
sess.get("theme", "light")      # read with a default
sess["locale"] = "en"           # persist across requests
"cart" in sess                  # presence
```

Because it is a plain dict, everything you know about dicts applies — no special store API to learn.

## Flash data

Flash data lives in the session for **exactly one** subsequent request, then ages out — the classic
"post/redirect/get" notice. Flash a value onto a redirect on the way out:

```python
from arvel import redirect

return redirect().route("posts.index").with_("status", "Post created")
```

On the next request, read it back from the flash bag and hand it to the view (unlike `errors`/`old`
below, arbitrary flash keys are not auto-shared — pass them explicitly):

```python
from arvel import view
from arvel.http import session
from arvel.http.flash import FlashBag

async def index(request):
    status = FlashBag(session()).pull("status")
    return await view("posts/index", {"status": status}).to_response()
```

```html
{% if status %}<div class="alert">{{ status }}</div>{% endif %}
```

To flash imperatively, wrap the session dict in a `FlashBag`:

```python
from arvel.http import session
from arvel.http.flash import FlashBag

bag = FlashBag(session())
bag.flash("status", "Saved")          # one-request value
count = bag.pull("attempts", 0)       # read + remove
bag.increment("visits")               # counters that persist
bag.decrement("credits", 2)
```

### Old input

When validation fails you redirect back and repopulate the form. `with_input()` stashes the request
body; the `old()` helper reads a field back on the next request (see [Validation](validation.md)):

```python
return redirect().back().with_input().with_errors(validator.errors())
```

The `ShareErrorsFromSession` step shares `errors` and `old` with every view for that next request, so
templates read them directly — no controller plumbing:

```html
<input name="title" value="{{ old('title') }}">
{% if errors.title %}<span class="error">{{ errors.title[0] }}</span>{% endif %}
```

### Keeping flash data for another request

If a value needs to survive a second hop (e.g. an extra redirect), keep it fresh:

```python
bag.reflash()                    # keep all flash data one more request
bag.keep(["status"])             # keep just these keys
bag.flash_only(data, ["email"])  # flash only a subset of a dict
```

## See also

- [Validation](validation.md) — flashes errors and old input on failure.
- [Responses](responses.md) — `redirect().with_(...)`/`with_input()`/`with_errors()`.
- [CSRF Protection](csrf.md) — the session token that guards state-changing requests.
