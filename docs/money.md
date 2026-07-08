# Money

Working with money as `float` loses pennies. `Money` is an **immutable, currency-aware value object**
that stores the amount in **integer minor units** (cents) — a faithful port of
[moneyphp/money](https://www.moneyphp.org/). Arithmetic across different currencies raises, and
`allocate` splits an amount **without ever losing a unit**.

```python
from arvel.support import Money

price = Money.of("19.99", "USD")   # from major units → 1999 minor units
price.amount                        # 1999  (minor units, an int)
price.major()                       # Decimal('19.99')
str(price)                          # "$19.99"   (str() == .format())
```

`Money(1999, "USD")` constructs from **minor** units directly; `Money.of(...)` from **major** units
(rounding half-up). Currency precision comes from the locale data, so `Money.of(1500, "JPY")` is
`1500` (JPY has no minor unit) while USD has two.

## Arithmetic

```python
Money.of("19.99", "USD").times(3)              # $59.97
Money(500, "USD") + Money(200, "USD")          # $7.00   (plus)
Money(500, "USD") - Money(200, "USD")          # $3.00   (minus)
-Money(5, "USD"); Money(-5, "USD").absolute()  # negate / absolute

Money(1, "USD") + Money(1, "EUR")              # ValueError — currency mismatch
```

`times` rounds the result half-up, so `Money(100, "USD").times("1.005")` is `101`.

## Allocation (penny-perfect)

Split a total by ratios; the leftover minor units go to the largest fractional shares, so the parts
always sum back to the original:

```python
Money(1000, "USD").allocate([1, 1, 1])   # [$3.34, $3.33, $3.33]  → sums to $10.00
Money(1005, "USD").allocate([3, 7])      # [$3.02, $7.03]
Money(10, "USD").allocate_to(3)          # even split → [4, 3, 3] cents
```

## Comparison & predicates

```python
Money(5, "USD") > Money(3, "USD")        # True  (also < <= >= and .compare() → -1/0/1)
Money(5, "USD").equals(Money(5, "USD"))  # True  (False across currencies)
Money(0, "USD").is_zero()                # is_positive() / is_negative()
```

Comparisons across currencies raise (you can't order USD against EUR). `Money` is hashable, so it
works as a dict key or in a set.

## Formatting

```python
Money.of("1234.5", "USD").format("en_US")   # "$1,234.50"
Money(1500, "JPY").format("ja_JP")          # "￥1,500"
```

`format()` with no argument uses the **active locale**, so money honors i18n automatically. Pass a
`locale` to override. (Babel, the `[i18n]` extra.)

### Internationalized amounts

The active locale is set per request by the `Locale` middleware (from the `Accept-Language` header),
or explicitly with `Lang.set_locale(...)`. The **same** `Money` then formats per locale (the `Lang`
facade resolves through the container, so this runs **within a booted arvel app**):

```python
from arvel.support import Money
from arvel.support.facades import Lang

price = Money.of("1234.50", "EUR")          # one stored amount

Lang.set_locale("en_US"); price.format()    # "€1,234.50"
Lang.set_locale("fr_FR"); price.format()    # "1 234,50 €"
Lang.set_locale("de_DE"); price.format()    # "1.234,50 €"
Lang.set_locale("ar_EG"); price.format()    # "‏1,234.50 €‏"   (Arabic — right-to-left)

price.format("en_US")                        # "€1,234.50" — an explicit locale still overrides
```

Arabic (and other RTL locales) also localizes the currency symbol — a Saudi-Riyal price renders with
the native symbol and digits:

```python
Lang.set_locale("ar_SA")
Money.of("1234.50", "SAR").format()          # "‏1,234.50 ر.س.‏"
```

So a price stored once (minor units + currency) renders correctly for every user's locale — RTL
included — with no locale threading through your code. The `Number` helpers (`Number.currency`,
`Number.format`) follow the same active-locale rule — see [Helpers](helpers.md).

## Common mistakes & gotchas

- **`Money(1999, ...)` vs `Money.of("19.99", ...)`.** The constructor takes **minor** units (cents);
  `.of()` takes **major** units. `Money(1999, "USD")` and `Money.of("19.99", "USD")` are the same
  amount — mixing them up is off by 100×.
- **Building `Money` from a `float`.** Pass a string or `Decimal` to `.of()`; a `float` like `19.99`
  is already imprecise before `Money` ever sees it. The whole point is to never touch binary floats.
- **Mixing currencies.** Arithmetic and comparison across currencies raise by design — convert to a
  common currency first; there's no implicit FX.
- **Splitting with plain division.** Dividing a total in your own code re-introduces lost pennies.
  Use `allocate`/`allocate_to`, which distribute the remainder so the parts sum back to the original.
- **Assuming two decimal places.** Precision is per-currency (JPY has none). Don't hardcode `/100` —
  use `.major()` / `.format()`.

## See also

- [Helpers](helpers.md) — `Number` for non-currency formatting.
- [Localization](localization.md) — locales drive currency formatting.
