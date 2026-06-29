"""T1.6 — support (Collection/Str), dates (whenever), localization (Translator)."""

from __future__ import annotations

from whenever import ZonedDateTime

from arvel.dates import Date, now, today
from arvel.localization import Translator, current_locale, plural_category, trans, trans_choice
from arvel.support import Collection, Str


# --- support: Collection ---------------------------------------------------
def test_collection_pipeline() -> None:
    c = Collection([1, 2, 3, 4])
    assert c.map(lambda x: x * 2).all() == [2, 4, 6, 8]
    assert c.filter(lambda x: x % 2 == 0).all() == [2, 4]
    assert c.reduce(lambda acc, x: acc + x, 0) == 10
    assert c.sum() == 10
    assert c.first() == 1
    assert c.last() == 4
    assert c.count() == 4
    assert c.contains(3) is True
    assert Collection([3, 1, 2]).sort().all() == [1, 2, 3]
    assert Collection([1, 1, 2]).unique().all() == [1, 2]
    assert Collection().is_empty() is True


def test_collection_pluck_and_where() -> None:
    rows = [{"id": 1, "role": "a"}, {"id": 2, "role": "b"}, {"id": 3, "role": "a"}]
    c = Collection(rows)
    assert c.pluck("id").all() == [1, 2, 3]
    assert c.where("role", "a").pluck("id").all() == [1, 3]


# --- support: Str ----------------------------------------------------------
def test_str_helpers() -> None:
    assert Str.studly("foo_bar") == "FooBar"
    assert Str.camel("foo_bar") == "fooBar"
    assert Str.snake("FooBar") == "foo_bar"
    assert Str.kebab("FooBar") == "foo-bar"
    assert Str.slug("Hello World!") == "hello-world"
    assert Str.plural("post") == "posts"
    assert Str.singular("posts") == "post"
    assert len(Str.ulid()) == 26
    assert Str.limit("hello world", 5) == "hello..."


# --- dates: whenever-backed ------------------------------------------------
def test_now_today_are_dates() -> None:
    assert isinstance(now("UTC"), Date)
    assert isinstance(today("UTC"), Date)
    assert isinstance(now("UTC").raw, ZonedDateTime)


def test_iso_roundtrip_and_add() -> None:
    d = now("UTC")
    assert Date.parse(d.to_iso()).to_iso() == d.to_iso()
    assert d.add_days(1).to_iso() != d.to_iso()


def test_is_weekend() -> None:
    sat = Date(ZonedDateTime(2024, 3, 30, 12, tz="Europe/London"))
    mon = Date(ZonedDateTime(2024, 4, 1, 12, tz="Europe/London"))
    assert sat.is_weekend() is True and sat.is_weekday() is False  # Sat (default weekend)
    assert mon.is_weekend() is False and mon.is_weekday() is True  # Mon


def test_weekend_days_are_configurable() -> None:
    """Many countries rest Fri/Sat, not Sat/Sun — config('app.weekend_days') overrides the default."""
    from arvel.kernel import Application, set_application

    fri = Date(ZonedDateTime(2024, 3, 29, 12, tz="UTC"))  # Friday
    sun = Date(ZonedDateTime(2024, 3, 31, 12, tz="UTC"))  # Sunday
    # default: Fri is a weekday, Sun is weekend
    assert fri.is_weekend() is False and sun.is_weekend() is True
    app = Application()
    app.make("config").set("app.weekend_days", ["friday", "saturday"])
    set_application(app)
    try:
        assert fri.is_weekend() is True  # now a weekend day
        assert sun.is_weekend() is False  # Sunday is now a working day
    finally:
        set_application(None)


def test_set_test_now_freezes() -> None:
    frozen = now("UTC")
    Date.set_test_now(frozen)
    try:
        assert now().to_iso() == frozen.to_iso()
    finally:
        Date.set_test_now(None)


def test_diff_for_humans() -> None:
    base = now("UTC")
    assert "hour" in base.add(hours=3).diff_for_humans(base)


# --- localization ----------------------------------------------------------
def test_translator_get_with_replace_and_fallback() -> None:
    t = Translator({"en": {"messages": {"welcome": "Welcome, {name}"}}}, fallback="en")
    assert t.get("messages.welcome", {"name": "Ada"}, locale="en") == "Welcome, Ada"
    assert t.get("messages.welcome", {"name": "Ada"}, locale="fr") == "Welcome, Ada"  # fallback
    assert t.get("missing.key", locale="en") == "missing.key"


def test_translator_json_flat_keys() -> None:
    t = Translator({"fr": {"Save": "Enregistrer"}})
    assert t.get("Save", locale="fr") == "Enregistrer"


def test_translator_choice() -> None:
    t = Translator({"en": {"apples": "one apple|many apples"}})
    assert t.choice("apples", 1, locale="en") == "one apple"
    assert t.choice("apples", 5, locale="en") == "many apples"


def test_locale_contextvar() -> None:
    t = Translator()
    token = current_locale.set("en")
    try:
        t.set_locale("fr")
        assert t.get_locale() == "fr"
    finally:
        current_locale.reset(token)


def test_plural_category_uses_babel() -> None:
    assert plural_category("pl", 2) == "few"
    assert plural_category("en", 2) == "other"


def test_helpers_use_default_translator() -> None:
    assert trans("nope.key") == "nope.key"
    assert "apple" in trans_choice("x", 1) or trans_choice("x", 1) == "x"
