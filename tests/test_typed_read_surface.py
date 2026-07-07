"""The ORM read surface is generically typed: a model-bound query hydrates as
the model to the type checker, not Any. Verified by running mypy over a tiny
typed consumer and asserting its reveal_type output."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path


def test_query_reads_infer_the_model_type(tmp_path: Path) -> None:
    sample = tmp_path / "typed_consumer.py"
    sample.write_text(
        textwrap.dedent(
            """
            from arvel.database import Model


            class Book(Model):
                __fields__ = {"title": str}
                __fillable__ = ["title"]


            async def flow() -> None:
                reveal_type(await Book.query().first())
                reveal_type(await Book.where("title", "=", "x").get())
                reveal_type(await Book.query().sole())
            """
        )
    )
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--follow-imports=silent", str(sample)],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    out = result.stdout
    assert 'Revealed type is "typed_consumer.Book | None"' in out, out
    assert "ModelCollection[typed_consumer.Book]" in out, out
    assert 'Revealed type is "typed_consumer.Book"' in out, out
