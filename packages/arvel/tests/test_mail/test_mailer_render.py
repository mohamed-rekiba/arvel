"""Tests for ``Mailer`` rendering — the four ``Content`` shapes and the
HTML-to-text auto-derivation when only HTML is provided.

Renders are observed through ``ArrayMailDriver.sent`` rather than calling
``Mailer._render`` directly, keeping the test on the public surface.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from arvel.config._lookup_registry import register, reset
from arvel.mail.config import MailConfig
from arvel.mail.content import Content
from arvel.mail.drivers.array import ArrayMailDriver
from arvel.mail.envelope import Envelope
from arvel.mail.mailable import Mailable
from arvel.mail.mailer import Mailer
from arvel.support import view as view_module


@pytest.fixture
def template_dir(tmp_path: Path) -> Path:
    (tmp_path / "welcome.txt.j2").write_text("Hi {{ name }} — welcome.\n")
    (tmp_path / "welcome.html.j2").write_text(
        "<p>Hi <strong>{{ name }}</strong> — welcome.</p>\n",
    )
    return tmp_path


@pytest.fixture
def view_config(template_dir: Path) -> Iterator[None]:
    fake = ModuleType("view")
    fake.paths = [str(template_dir)]  # type: ignore[attr-defined]
    reset()
    register("view", fake)
    view_module.reset_cache()
    try:
        yield
    finally:
        reset()
        view_module.reset_cache()


@pytest.fixture
def driver() -> ArrayMailDriver:
    return ArrayMailDriver()


@pytest.fixture
def mailer(driver: ArrayMailDriver) -> Mailer:
    return Mailer(driver, MailConfig(default="array"))


def _build_mailable(content: Content) -> Mailable:
    """Tiny ad-hoc mailable used by every render test below."""

    class _Mail(Mailable):
        def envelope(self) -> Envelope:
            return Envelope(from_address="a@b.com", to=["c@d.com"], subject="Test")

        def content(self) -> Content:
            return content

    return _Mail()


class TestMailerRender:
    @pytest.mark.asyncio
    async def test_inline_text_only(self, driver: ArrayMailDriver, mailer: Mailer) -> None:
        await mailer.send_to("to@example.com", _build_mailable(Content(text="Hello.")))
        assert len(driver.sent) == 1
        rendered = driver.sent[0]
        assert rendered.body_text == "Hello."
        assert rendered.body_html is None

    @pytest.mark.asyncio
    async def test_inline_html_only_auto_derives_text(
        self, driver: ArrayMailDriver, mailer: Mailer
    ) -> None:
        await mailer.send_to(
            "to@example.com",
            _build_mailable(Content(html="<p>Hello world.</p>")),
        )
        rendered = driver.sent[0]
        assert rendered.body_html == "<p>Hello world.</p>"
        assert rendered.body_text == "Hello world."

    @pytest.mark.asyncio
    async def test_inline_text_and_html(self, driver: ArrayMailDriver, mailer: Mailer) -> None:
        await mailer.send_to(
            "to@example.com",
            _build_mailable(
                Content(text="Plain hello.", html="<p>HTML hello.</p>"),
            ),
        )
        rendered = driver.sent[0]
        assert rendered.body_text == "Plain hello."
        assert rendered.body_html == "<p>HTML hello.</p>"

    @pytest.mark.asyncio
    async def test_text_view_template(
        self, view_config: None, driver: ArrayMailDriver, mailer: Mailer
    ) -> None:
        await mailer.send_to(
            "to@example.com",
            _build_mailable(
                Content(text_view="welcome.txt.j2", data={"name": "Ada"}),
            ),
        )
        rendered = driver.sent[0]
        assert rendered.body_text == "Hi Ada — welcome.\n"
        assert rendered.body_html is None

    @pytest.mark.asyncio
    async def test_html_view_template_autoescapes_data(
        self, view_config: None, driver: ArrayMailDriver, mailer: Mailer
    ) -> None:
        await mailer.send_to(
            "to@example.com",
            _build_mailable(
                Content(html_view="welcome.html.j2", data={"name": "<script>"}),
            ),
        )
        rendered = driver.sent[0]
        assert rendered.body_html is not None
        assert "&lt;script&gt;" in rendered.body_html
        # Auto-derived plain text strips tags but keeps the (escaped) entity
        #  i.e. the user's literal "<script>" appears in the text fallback.
        assert "<script>" in rendered.body_text

    @pytest.mark.asyncio
    async def test_both_views_share_template_context(
        self, view_config: None, driver: ArrayMailDriver, mailer: Mailer
    ) -> None:
        await mailer.send_to(
            "to@example.com",
            _build_mailable(
                Content(
                    text_view="welcome.txt.j2",
                    html_view="welcome.html.j2",
                    data={"name": "Ada"},
                ),
            ),
        )
        rendered = driver.sent[0]
        assert "Ada" in rendered.body_text
        assert rendered.body_html is not None
        assert "Ada" in rendered.body_html

    @pytest.mark.asyncio
    async def test_send_to_overrides_recipients(
        self, driver: ArrayMailDriver, mailer: Mailer
    ) -> None:
        await mailer.send_to("override@example.com", _build_mailable(Content(text="x")))
        rendered = driver.sent[0]
        assert rendered.envelope.to == ["override@example.com"]

    @pytest.mark.asyncio
    async def test_inherits_global_from_when_envelope_omits_it(
        self, driver: ArrayMailDriver
    ) -> None:
        """Laravel parity: a mailable that omits ``from`` inherits ``mail.from``."""
        mailer = Mailer(
            driver,
            MailConfig(default="array", from_address="global@x.com", from_name="Global Sender"),
        )

        class _Mail(Mailable):
            def envelope(self) -> Envelope:
                return Envelope(to=["c@d.com"], subject="Hi")

            def content(self) -> Content:
                return Content(text="x")

        await mailer.send_to("c@d.com", _Mail())
        rendered = driver.sent[0]
        assert rendered.envelope.from_address == "global@x.com"
        assert rendered.envelope.from_name == "Global Sender"

    @pytest.mark.asyncio
    async def test_envelope_from_overrides_global(self, driver: ArrayMailDriver) -> None:
        """An explicit envelope ``from`` wins over the global default."""
        mailer = Mailer(
            driver,
            MailConfig(default="array", from_address="global@x.com", from_name="Global"),
        )

        class _Mail(Mailable):
            def envelope(self) -> Envelope:
                return Envelope(from_address="explicit@x.com", to=["c@d.com"], subject="Hi")

            def content(self) -> Content:
                return Content(text="x")

        await mailer.send_to("c@d.com", _Mail())
        rendered = driver.sent[0]
        assert rendered.envelope.from_address == "explicit@x.com"
