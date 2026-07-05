# Feature Flags

Feature flags let you ship code behind a switch — roll a change out to one user, one team, or
everyone, without a deploy for every flip. arvel's feature-flag module follows
[Laravel Pennant](https://laravel.com/docs/pennant): define a flag once with a **resolver**, then
ask whether it's active for a given **scope** (a user, a team, or nothing at all for a global
flag).

A resolver runs **at most once per scope** — the first `active()`/`value()` call for a scope
resolves it and writes the result to the configured store; every call after that (for that same
scope) is served straight from the store, not re-computed.

!!! note "Backends"
    The in-process `array` driver is the default and needs nothing — great for tests. `database`
    persists resolved values in a `features` table (survives a restart); `cache` stores them in
    the [cache](cache.md) (story 06), tagged per flag so purging one flag never touches another's
    stored values. Set `features.driver`.

## Defining a flag

```python
from arvel.features import Feature

Feature.define("new-dashboard", lambda scope: scope.is_beta_tester)
```

The resolver receives whatever `scope` you resolve the flag against and returns `bool | str | Any`
— a rich value, not just a boolean (see [Rich values](#rich-values) below). Register your flags in
a service provider's `boot()`, the same place you'd register routes or event listeners.

A **class-based feature** works too — it's instantiated once and dispatched through `.resolve`:

```python
class NewDashboard:
    def resolve(self, scope: Any) -> bool:
        return scope.is_beta_tester

Feature.define("new-dashboard", NewDashboard)
```

## Checking a flag

```python
await Feature.active("new-dashboard", user)     # bool
await Feature.inactive("new-dashboard", user)    # not active
await Feature.for_(user).active("new-dashboard") # same thing, scope bound up front
```

`scope=None` (the default) resolves the flag globally — every caller shares the same stored
value, keyed by `features.default_scope` (`"__global__"` unless you change it).

## Rich values

A resolver isn't limited to `bool` — return a variant string, a rollout percentage, anything
JSON-able:

```python
Feature.define("checkout-variant", lambda scope: "purple" if scope.id % 2 else "orange")

await Feature.value("checkout-variant", user)   # "purple" / "orange"
await Feature.active("checkout-variant", user)  # True — active() is just truthiness
```

## `when` — branch on the resolved value

```python
await Feature.when(
    "checkout-variant", user,
    lambda variant: render(variant),   # called with the resolved value when active/truthy
    lambda variant: render_default(),  # called when falsy
)
```

## Overriding a resolver

`activate`/`deactivate` write directly to the store, bypassing the resolver entirely — useful for
an admin toggle or a test:

```python
await Feature.activate("new-dashboard", user)            # force it on
await Feature.deactivate("new-dashboard", user)           # force it off
await Feature.activate("checkout-variant", user, value="purple")  # force a rich value
```

`forget` clears one scope's stored value (the resolver runs again next time it's checked);
`purge` clears **every** stored scope for a flag — reach for it after changing a resolver's logic:

```python
await Feature.forget("new-dashboard", user)   # this user only
await Feature.purge("new-dashboard")          # every scope, everywhere
```

## CLI

```bash
arvel feature:list          # every flag registered via Feature.define()
arvel feature:purge <name>  # clear every stored value for <name>
```

## Configuration

```python
# config/features.py
config = {
    "driver": "database",       # "array" | "database" | "cache"
    "default_scope": "__global__",
}
```
