"""Shared test helpers — a searchable model and a deterministic config builder.

Kept out of ``conftest`` so the import has a repo-unique module name; bare
``from conftest import`` would force mypy to unify every package's ``conftest``.
"""

from __future__ import annotations

from arvel.database import Model
from arvel_search import SearchConfig
from arvel_search.searchable import Searchable
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class Article(Model, Searchable):
    __tablename__ = "search_articles"
    __searchable__ = ("title", "body")

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="general")


def make_config(**overrides: object) -> SearchConfig:
    """Build a SearchConfig from explicit values, ignoring ambient env/.env.

    ``model_validate`` bypasses BaseSettings' env sources, so tests are
    deterministic regardless of the developer's shell.
    """
    return SearchConfig.model_validate(overrides)
