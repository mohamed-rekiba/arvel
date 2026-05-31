"""Shell REPL — extended namespace, model auto-import, and DB facade wiring.

These tests cover the post-WI-021 enhancements: the expanded facade set, user
model auto-import from ``app/models/*.py``, banner output, and the DB facade
fallback wiring done in ``DatabaseServiceProvider.boot()``.
"""

from __future__ import annotations

import os
import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from arvel.application import Application, ApplicationBuilder
from arvel.console.commands.shell import ShellCommand
from arvel.database import DB
from arvel.providers import ConfigServiceProvider, DatabaseServiceProvider


@pytest.fixture
def db_env(tmp_app_path: Path) -> Iterator[Path]:
    """Snapshot os.environ + point DB_CONNECTION at in-memory SQLite + return tmp app dir."""
    snapshot = dict(os.environ)
    os.environ["DB_CONNECTION"] = "memory"
    try:
        yield tmp_app_path
    finally:
        os.environ.clear()
        os.environ.update(snapshot)


def _build_app(base_path: Path) -> Application:
    return (
        ApplicationBuilder(base_path=base_path)
        .with_providers([ConfigServiceProvider, DatabaseServiceProvider])
        .create()
    )


# ─────────────────────────────────────────────────────────────────────────────
# Expanded facade set in the REPL namespace
# ─────────────────────────────────────────────────────────────────────────────


class TestExpandedFacades:
    """Every public facade reachable in this environment is exposed in the REPL.

    The 5-facade set predated the queue, storage, mail, notification, broadcast,
    event, hash, and DB facades — exposing them now matches the Laravel Tinker
    user expectation that "everything that's bound is reachable from the REPL".
    """

    _EXPECTED_FACADES = (
        "Cache",
        "Auth",
        "Bus",
        "Config",
        "Session",
        "Storage",
        "Mail",
        "Notification",
        "Broadcast",
        "Event",
        "Hash",
        "DB",
    )

    def test_namespace_includes_extended_facade_set(self, db_env: Path) -> None:
        framework_app = _build_app(db_env)
        cmd = ShellCommand()
        cmd.app = framework_app
        try:
            ns = cmd.build_namespace()
            missing = [f for f in self._EXPECTED_FACADES if f not in ns]
            assert not missing, f"Missing facades: {missing}; got: {sorted(ns)}"
        finally:
            cmd.release_active_session()


# ─────────────────────────────────────────────────────────────────────────────
# User model auto-import from app/models/*.py
# ─────────────────────────────────────────────────────────────────────────────


class TestAutoImportUserModels:
    """The REPL should pre-import user ORM models so newcomers can type
    ``User.query()`` without first writing ``from app.models.user import User``."""

    def test_imports_model_subclasses_into_namespace(self, db_env: Path) -> None:
        models_dir = db_env / "app" / "models"
        models_dir.mkdir(parents=True)
        (models_dir / "post.py").write_text(
            textwrap.dedent(
                """
                from __future__ import annotations

                from arvel.database import Model, id_


                class Post(Model):
                    __tablename__ = "shell_ext_posts"
                    id: int = id_()
                """
            )
        )

        cmd = ShellCommand()
        cmd.app = _build_app(db_env)
        try:
            ns = cmd.build_namespace()
            from arvel.database import Model

            assert "Post" in ns
            assert isinstance(ns["Post"], type)
            assert issubclass(ns["Post"], Model)
            assert ns["__arvel_aliased_models__"] == ("Post",)
        finally:
            cmd.release_active_session()

    def test_skips_broken_model_file_without_crashing(
        self, db_env: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        models_dir = db_env / "app" / "models"
        models_dir.mkdir(parents=True)
        (models_dir / "broken.py").write_text("this is not valid python !!!\n")
        (models_dir / "tag.py").write_text(
            textwrap.dedent(
                """
                from __future__ import annotations

                from arvel.database import Model, id_


                class Tag(Model):
                    __tablename__ = "shell_ext_tags"
                    id: int = id_()
                """
            )
        )

        cmd = ShellCommand()
        cmd.app = _build_app(db_env)
        try:
            import logging

            with caplog.at_level(logging.WARNING, logger="arvel.console.shell"):
                ns = cmd.build_namespace()
            assert "Tag" in ns
            assert "Broken" not in ns
            assert any("broken.py" in r.message for r in caplog.records)
        finally:
            cmd.release_active_session()

    def test_existing_namespace_keys_win_on_collision(self, db_env: Path) -> None:
        models_dir = db_env / "app" / "models"
        models_dir.mkdir(parents=True)
        # A user model named ``Cache`` would shadow the Cache facade — refuse
        # to overwrite. First definition (the facade) wins.
        (models_dir / "cache.py").write_text(
            textwrap.dedent(
                """
                from __future__ import annotations

                from arvel.database import Model, id_


                class Cache(Model):
                    __tablename__ = "shell_ext_cache"
                    id: int = id_()
                """
            )
        )

        cmd = ShellCommand()
        cmd.app = _build_app(db_env)
        try:
            ns = cmd.build_namespace()
            from arvel.facades.cache import Cache as CacheFacade

            assert ns["Cache"] is CacheFacade  # facade not overwritten
            # And the user's Cache model is NOT counted as an aliased model.
            assert "Cache" not in ns.get("__arvel_aliased_models__", ())
        finally:
            cmd.release_active_session()

    def test_no_models_dir_is_a_silent_noop(self, db_env: Path) -> None:
        # db_env has no app/ subdir at all.
        cmd = ShellCommand()
        cmd.app = _build_app(db_env)
        try:
            ns = cmd.build_namespace()
            assert "__arvel_aliased_models__" not in ns
            assert "session" in ns  # still got the session-binding behaviour
        finally:
            cmd.release_active_session()

    def test_init_py_in_models_dir_is_ignored(self, db_env: Path) -> None:
        """An empty ``app/models/__init__.py`` shouldn't be parsed as a model file."""
        models_dir = db_env / "app" / "models"
        models_dir.mkdir(parents=True)
        (models_dir / "__init__.py").write_text("")

        cmd = ShellCommand()
        cmd.app = _build_app(db_env)
        try:
            ns = cmd.build_namespace()
            assert "__arvel_aliased_models__" not in ns
        finally:
            cmd.release_active_session()


# ─────────────────────────────────────────────────────────────────────────────
# Banner output
# ─────────────────────────────────────────────────────────────────────────────


class TestShellBanner:
    """The banner should announce session/transaction semantics so the user knows
    they need to commit explicitly — matches Laravel Tinker's "no implicit save"
    contract."""

    def test_banner_mentions_session_when_db_bound(
        self, db_env: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cmd = ShellCommand()
        cmd.app = _build_app(db_env)
        try:
            ns = cmd.build_namespace()
            cmd.print_banner(ns)
            out = capsys.readouterr().out
            assert "Arvel shell" in out
            assert "DB session active" in out
            assert "DB.transaction" in out or "session.commit" in out
        finally:
            cmd.release_active_session()

    def test_banner_lists_aliased_models(
        self, db_env: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        models_dir = db_env / "app" / "models"
        models_dir.mkdir(parents=True)
        (models_dir / "article.py").write_text(
            textwrap.dedent(
                """
                from __future__ import annotations

                from arvel.database import Model, id_


                class Article(Model):
                    __tablename__ = "shell_ext_articles"
                    id: int = id_()
                """
            )
        )

        cmd = ShellCommand()
        cmd.app = _build_app(db_env)
        try:
            ns = cmd.build_namespace()
            cmd.print_banner(ns)
            out = capsys.readouterr().out
            assert "Aliased models" in out
            assert "Article" in out
        finally:
            cmd.release_active_session()


# ─────────────────────────────────────────────────────────────────────────────
# DatabaseServiceProvider.boot() configures the DB facade's session maker
# ─────────────────────────────────────────────────────────────────────────────


def _reset_db_facade(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset ``DB`` process-global session-maker state in a snapshot-restore-safe
    way. Uses ``monkeypatch.setattr`` with a string attribute so pyright doesn't
    flag access to the private name from the test."""
    monkeypatch.setattr(DB, "_session_maker", None, raising=False)


class TestDatabaseProviderConfiguresDBFacade:
    """``DB.transaction()`` and ``DB.select(...)`` from CLI commands (outside
    HTTP middleware scope) need a session maker on the DB facade. After
    ``DatabaseServiceProvider.boot()``, that maker MUST be configured.

    Verified by behaviour: ``DB.select(...)`` must succeed outside any HTTP
    request scope. Pre-fix, the call raised
    ``RuntimeError: TableQueryBuilder requires an active DB session`` because
    the facade's session-maker was never populated for CLI contexts.
    """

    @pytest.mark.asyncio
    async def test_db_select_works_after_boot_outside_request_scope(
        self, db_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _reset_db_facade(monkeypatch)
        framework_app = _build_app(db_env)
        await framework_app.boot()
        rows = await DB.select("SELECT 1 AS one")
        assert rows == [{"one": 1}]


# ─────────────────────────────────────────────────────────────────────────────
# IPython integration: the namespace flows through to user-typed code
# ─────────────────────────────────────────────────────────────────────────────


class TestIPythonNamespaceWiring:
    """The namespace built by ``build_namespace()`` must be reachable from
    code typed at the REPL prompt. IPython's ``embed()`` is fussy about
    which kwarg name it accepts (``user_ns``, not ``local_ns``) — and the
    wrong name is silently dropped without error. This test instantiates a
    real ``InteractiveShellEmbed`` with the same kwargs the command uses and
    confirms that aliased model names actually resolve.
    """

    def test_aliased_model_resolves_inside_ipython_user_ns(self, db_env: Path) -> None:
        # IPython is an untyped third-party dep; narrow at this boundary.
        ipython_embed: Any = pytest.importorskip("IPython.terminal.embed")
        InteractiveShellEmbed: Any = ipython_embed.InteractiveShellEmbed

        models_dir = db_env / "app" / "models"
        models_dir.mkdir(parents=True)
        (models_dir / "widget.py").write_text(
            textwrap.dedent(
                """
                from __future__ import annotations

                from arvel.database import Model, id_


                class Widget(Model):
                    __tablename__ = "shell_ext_widgets"
                    id: int = id_()
                """
            )
        )

        cmd = ShellCommand()
        cmd.app = _build_app(db_env)
        try:
            ns = cmd.build_namespace()
            # Instantiate the same singleton ``embed()`` uses internally,
            # passing the namespace the way the production code does.
            InteractiveShellEmbed.clear_instance()
            shell: Any = InteractiveShellEmbed.instance(user_ns=ns)
            try:
                # ``Widget`` was auto-imported by build_namespace() and must
                # resolve in the embedded shell's user namespace.
                user_ns: dict[str, Any] = shell.user_ns
                assert "Widget" in user_ns
                assert user_ns["Widget"] is ns["Widget"]
                # The facade set must also flow through.
                for facade_name in ("DB", "Cache", "Auth", "Config"):
                    assert facade_name in user_ns, f"{facade_name} missing from IPython user_ns"
            finally:
                InteractiveShellEmbed.clear_instance()
        finally:
            cmd.release_active_session()
