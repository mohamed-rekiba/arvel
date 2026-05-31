"""Shared test helpers — a searchable model and a deterministic config builder.

Kept out of ``conftest`` so the import has a repo-unique module name; bare
``from conftest import`` would force mypy to unify every package's ``conftest``.
"""

from __future__ import annotations

from arvel.database import Model, id_, string
from arvel_search import SearchConfig
from arvel_search.searchable import Searchable


class Article(Model, Searchable):
    __tablename__ = "search_articles"
    __searchable__ = ("title", "body")

    id: int = id_()
    title: str = string(200)
    body: str = string(2000)
    category: str = string(50, default="general")


def make_config(**overrides: object) -> SearchConfig:
    """Build a SearchConfig from explicit values, ignoring ambient env/.env.

    ``model_validate`` bypasses BaseSettings' env sources, so tests are
    deterministic regardless of the developer's shell.
    """
    return SearchConfig.model_validate(overrides)
