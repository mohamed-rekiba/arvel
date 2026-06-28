"""arvel.support.number — locale-aware number formatting on Babel (L10 parity).

Babel is lazy-imported inside the methods (the ``[i18n]`` tier) so importing
``arvel.support`` stays light. ``locale`` defaults to the **active locale**
(``current_locale`` — set by ``Lang::set_locale`` / the Locale middleware), so formatting honors
i18n out of the box; pass ``locale`` to override. Grounded in knowledge/port/06 §helpers.
"""

from __future__ import annotations


def _locale(locale: str | None) -> str:
    if locale is not None:
        return locale
    from arvel.localization import current_locale

    return current_locale.get()


class Number:
    @staticmethod
    def format(value: float, locale: str | None = None) -> str:
        from babel.numbers import format_decimal

        return format_decimal(value, locale=_locale(locale))

    @staticmethod
    def currency(value: float, currency: str = "USD", locale: str | None = None) -> str:
        from babel.numbers import format_currency

        return format_currency(value, currency, locale=_locale(locale))

    @staticmethod
    def percentage(value: float, locale: str | None = None) -> str:
        from babel.numbers import format_percent

        return format_percent(value / 100, locale=_locale(locale))

    @staticmethod
    def human(value: float) -> str:
        for threshold, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
            if abs(value) >= threshold:
                text = f"{value / threshold:.1f}".rstrip("0").rstrip(".")
                return f"{text}{suffix}"
        return str(int(value)) if float(value).is_integer() else str(value)

    @staticmethod
    def abbreviate(value: float) -> str:
        """Compact K/M/B form — Laravel ``Number::abbreviate`` (alias of ``human``)."""
        return Number.human(value)

    @staticmethod
    def for_humans(value: float) -> str:
        """Full-word magnitude — Laravel ``Number::forHumans`` (1500 → ``1.5 thousand``)."""
        for threshold, word in (
            (1_000_000_000_000, "trillion"),
            (1_000_000_000, "billion"),
            (1_000_000, "million"),
            (1_000, "thousand"),
        ):
            if abs(value) >= threshold:
                text = f"{value / threshold:.1f}".rstrip("0").rstrip(".")
                return f"{text} {word}"
        return str(int(value)) if float(value).is_integer() else str(value)

    @staticmethod
    def ordinal(number: int) -> str:
        """Ordinal form — Laravel ``Number::ordinal`` (1 → ``1st``, 22 → ``22nd``)."""
        n = int(number)
        if 11 <= (abs(n) % 100) <= 13:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(abs(n) % 10, "th")
        return f"{n}{suffix}"

    @staticmethod
    def file_size(bytes_: float, precision: int = 0) -> str:
        """Human file size (1024-based) — Laravel ``Number::fileSize`` (1024 → ``1 KB``)."""
        units = ("B", "KB", "MB", "GB", "TB", "PB")
        size = float(bytes_)
        index = 0
        while size >= 1024 and index < len(units) - 1:
            size /= 1024
            index += 1
        return f"{size:.{precision}f} {units[index]}"

    @staticmethod
    def clamp(value: float, minimum: float, maximum: float) -> float:
        """Constrain ``value`` to ``[minimum, maximum]`` — Laravel ``Number::clamp``."""
        return maximum if value > maximum else (minimum if value < minimum else value)

    @staticmethod
    def trim(value: float) -> float:
        """Drop trailing zeros — Laravel ``Number::trim`` (12.0 → 12, 12.30 → 12.3)."""
        number = float(value)
        return int(number) if number.is_integer() else number
