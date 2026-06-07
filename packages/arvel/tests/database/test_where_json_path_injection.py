"""where_json_path must bind the JSON key, so user input (e.g. a request
locale) can't break out of the SQL string.

The old implementation f-string-interpolated the key into the SQL text, so it
never appeared in the bound parameters. Binding it is what closes the hole —
these tests assert exactly that.
"""

from __future__ import annotations

from arvel.database import Model, id_, jsonb


class WidgetJ(Model):
    __tablename__ = "widgets_json_path"
    id: int = id_()
    slug: dict[str, str] = jsonb()


def test_json_key_is_a_bound_parameter() -> None:
    qb = WidgetJ.where_json_path("slug", "en", "shoes")
    bindings = qb.get_bindings(dialect="postgresql")
    assert "en" in bindings  # the key, bound — not interpolated
    assert "shoes" in bindings


def test_malicious_locale_travels_as_data_not_sql() -> None:
    payload = "en' OR '1'='1"
    qb = WidgetJ.where_json_path("slug", payload, "shoes")
    # If the key is bound, the whole payload arrives verbatim as one value
    # instead of fragmenting the SQL into an always-true OR clause.
    assert payload in qb.get_bindings(dialect="postgresql")
