"""Relations — eager-loading must batch (no N+1). Audit: `with_("articles")` should issue ONE
WHERE IN for the children across all parents (2 queries total), not one query per parent. Counted via
the connection's query log; a contrast test pins that lazy access really is N+1 (so with_ earns its keep)."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model


class Author(Model):
    __table_name__ = "authors"
    __fields__ = {"name": str}
    __fillable__ = ["name"]

    def articles(self) -> object:
        return self.has_many(Article)


class Article(Model):
    __table_name__ = "articles"
    __fields__ = {"title": str, "author_id": int}
    __fillable__ = ["title", "author_id"]


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (Author, Article):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    for i in range(5):
        author = await Author.create(name=f"a{i}")
        for j in range(3):
            await Article.create(title=f"t{i}{j}", author_id=author.id)
    return db


async def test_eager_load_batches_no_n_plus_1() -> None:
    db = await _setup()
    try:
        db.enable_query_log()  # resets the log; count only what the eager load issues
        authors = await Author.with_("articles").get()
        queries = len(db.get_query_log())
        # 5 authors x 3 articles: eager = authors query + ONE WHERE IN for articles = 2 (not 1+5)
        assert queries == 2, f"N+1! expected 2 queries, got {queries}"
        assert len(authors) == 5
        for author in authors:
            assert len(author.relation("articles")) == 3  # correctly grouped per parent
    finally:
        db.disable_query_log()
        await db.dispose()


async def test_lazy_access_is_n_plus_1_for_contrast() -> None:
    db = await _setup()
    try:
        authors = await Author.all()
        db.enable_query_log()
        for author in authors:
            await author.articles().get()
        # one query per author — the N+1 that with_() exists to eliminate
        assert len(db.get_query_log()) == 5
    finally:
        db.disable_query_log()
        await db.dispose()
