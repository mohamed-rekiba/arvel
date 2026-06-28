"""arvel.support.money — an immutable, currency-aware Money value object (moneyphp parity).

Amounts are stored as **integer minor units** (cents) to avoid float drift; arithmetic between
different currencies raises. ``allocate`` splits an amount by ratios **without losing a penny**
(the remainder is distributed to the largest fractional shares). Currency precision + formatting
come from Babel (the ``[i18n]`` tier), lazy-imported so ``import arvel`` stays light.

    from arvel.support import Money
    price = Money.of("19.99", "USD")        # 1999 minor units
    total = price.times(3)                    # $59.97
    a, b, c = Money(1000, "USD").allocate([1, 1, 1])   # 334 + 333 + 333 = 1000
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


class Currency:
    """An ISO-4217 currency code; ``minor_units`` is the number of decimal places (USD→2, JPY→0)."""

    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        self.code = code.upper()

    def minor_units(self) -> int:
        from babel.numbers import get_currency_precision

        try:
            return get_currency_precision(self.code)
        except Exception:
            return 2

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Currency) and other.code == self.code

    def __hash__(self) -> int:
        return hash(self.code)

    def __repr__(self) -> str:
        return f"Currency({self.code!r})"

    def __str__(self) -> str:
        return self.code


class Money:
    """An immutable monetary amount in a currency. Construct from **minor units**
    (``Money(1999, "USD")``) or major units (``Money.of("19.99", "USD")``)."""

    __slots__ = ("_amount", "_currency")

    def __init__(self, amount: int, currency: str | Currency) -> None:
        self._amount = int(amount)  # minor units (e.g. cents)
        self._currency = currency if isinstance(currency, Currency) else Currency(currency)

    @classmethod
    def of(cls, amount: int | float | str | Decimal, currency: str | Currency) -> Money:
        """Build from a **major-unit** amount (``"19.99"`` → 1999 cents), rounding half-up."""
        cur = currency if isinstance(currency, Currency) else Currency(currency)
        scale = Decimal(10) ** cur.minor_units()
        minor = (Decimal(str(amount)) * scale).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        return cls(int(minor), cur)

    # --- accessors ---------------------------------------------------------
    @property
    def amount(self) -> int:
        """The amount in **minor units** (integer)."""
        return self._amount

    @property
    def currency(self) -> Currency:
        return self._currency

    def major(self) -> Decimal:
        """The amount in **major units** as a ``Decimal`` (``1999`` USD → ``Decimal('19.99')``)."""
        return Decimal(self._amount) / (Decimal(10) ** self._currency.minor_units())

    # --- guards ------------------------------------------------------------
    def _assert_same_currency(self, other: Money) -> None:
        if self._currency != other._currency:
            raise ValueError(f"currency mismatch: {self._currency.code} vs {other._currency.code}")

    # --- arithmetic --------------------------------------------------------
    def plus(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self._amount + other._amount, self._currency)

    def minus(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self._amount - other._amount, self._currency)

    def times(self, factor: int | float | str | Decimal) -> Money:
        """Multiply by a scalar, rounding the resulting minor units half-up."""
        product = (Decimal(self._amount) * Decimal(str(factor))).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
        return Money(int(product), self._currency)

    def negative(self) -> Money:
        return Money(-self._amount, self._currency)

    def absolute(self) -> Money:
        return Money(abs(self._amount), self._currency)

    # --- allocation (penny-perfect) ----------------------------------------
    def allocate(self, ratios: list[int | float]) -> list[Money]:
        """Split into shares by ``ratios`` losing no minor unit — the remainder is handed out one
        unit at a time to the largest fractional shares (moneyphp ``allocate``)."""
        total = sum(ratios)
        if total <= 0:
            raise ValueError("cannot allocate: the sum of ratios must be greater than zero")
        if any(r < 0 for r in ratios):
            raise ValueError("cannot allocate: a ratio must be zero or positive")
        shares = [int(self._amount * ratio // total) for ratio in ratios]
        remainder = self._amount - sum(shares)
        fractions = [(self._amount * ratio / total) % 1 for ratio in ratios]
        # give the leftover units to the largest fractional parts (stable by original order on ties)
        for index in sorted(range(len(ratios)), key=lambda k: fractions[k], reverse=True):
            if remainder <= 0:
                break
            shares[index] += 1
            remainder -= 1
        return [Money(share, self._currency) for share in shares]

    def allocate_to(self, n: int) -> list[Money]:
        """Split evenly into ``n`` shares (penny-perfect)."""
        return self.allocate([1] * n)

    # --- comparison --------------------------------------------------------
    def compare(self, other: Money) -> int:
        """``-1`` / ``0`` / ``1`` (raises on a currency mismatch)."""
        self._assert_same_currency(other)
        return (self._amount > other._amount) - (self._amount < other._amount)

    def equals(self, other: object) -> bool:
        return (
            isinstance(other, Money)
            and self._currency == other._currency
            and self._amount == other._amount
        )

    def greater_than(self, other: Money) -> bool:
        return self.compare(other) > 0

    def greater_than_or_equal(self, other: Money) -> bool:
        return self.compare(other) >= 0

    def less_than(self, other: Money) -> bool:
        return self.compare(other) < 0

    def less_than_or_equal(self, other: Money) -> bool:
        return self.compare(other) <= 0

    def is_zero(self) -> bool:
        return self._amount == 0

    def is_positive(self) -> bool:
        return self._amount > 0

    def is_negative(self) -> bool:
        return self._amount < 0

    # --- formatting --------------------------------------------------------
    def format(self, locale: str | None = None) -> str:
        """Locale-aware currency string. Defaults to the **active locale** (``Lang::set_locale`` /
        the Locale middleware), so it honors i18n; pass ``locale`` to override.
        ``Money.of("19.99","USD").format()`` → ``"$19.99"`` under ``en``, ``"19,99 $US"`` under ``fr``."""
        from babel.numbers import format_currency

        from arvel.localization import current_locale

        return format_currency(
            self.major(), self._currency.code, locale=locale or current_locale.get()
        )

    # --- dunders -----------------------------------------------------------
    def __eq__(self, other: object) -> bool:
        return isinstance(other, Money) and self.equals(other)

    def __hash__(self) -> int:
        return hash((self._amount, self._currency))

    def __add__(self, other: Money) -> Money:
        return self.plus(other)

    def __sub__(self, other: Money) -> Money:
        return self.minus(other)

    def __mul__(self, factor: int | float | str | Decimal) -> Money:
        return self.times(factor)

    def __neg__(self) -> Money:
        return self.negative()

    def __lt__(self, other: Money) -> bool:
        return self.less_than(other)

    def __le__(self, other: Money) -> bool:
        return self.less_than_or_equal(other)

    def __gt__(self, other: Money) -> bool:
        return self.greater_than(other)

    def __ge__(self, other: Money) -> bool:
        return self.greater_than_or_equal(other)

    def __repr__(self) -> str:
        return f"Money({self._amount}, {self._currency.code!r})"

    def __str__(self) -> str:
        return self.format()
