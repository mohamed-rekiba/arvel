"""Tests for Mailable ABC."""

from __future__ import annotations

import pytest
from arvel.mail.attachment import Attachment
from arvel.mail.content import Content
from arvel.mail.envelope import Envelope
from arvel.mail.mailable import Mailable


class TestMailable:
    def test_mailable_is_abstract(self) -> None:
        cls: type = Mailable
        with pytest.raises(TypeError):
            cls()

    def test_concrete_mailable_requires_envelope_and_content(self) -> None:
        class M(Mailable):
            def envelope(self) -> Envelope:
                return Envelope(from_address="a@b.com", to=["c@d.com"], subject="Hi")

            def content(self) -> Content:
                return Content(text="body")

        m = M()
        assert m.envelope().subject == "Hi"
        assert m.content().text == "body"

    def test_attachments_default_is_empty_list(self) -> None:
        class M(Mailable):
            def envelope(self) -> Envelope:
                return Envelope(from_address="a@b.com", to=["c@d.com"], subject="Hi")

            def content(self) -> Content:
                return Content(text="body")

        assert M().attachments() == []

    def test_envelope_optional_fields(self) -> None:
        env = Envelope(
            from_address="a@b.com",
            to=["c@d.com"],
            subject="Test",
            cc=["d@e.com"],
            bcc=["f@g.com"],
            reply_to="h@i.com",
            tags=["transactional"],
        )
        assert env.cc == ["d@e.com"]
        assert env.tags == ["transactional"]

    def test_content_text_and_text_view_are_mutually_exclusive(self) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            Content(text="hi", text_view="welcome.txt.j2")

    def test_content_html_and_html_view_are_mutually_exclusive(self) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            Content(html="<p>hi</p>", html_view="welcome.html.j2")

    def test_content_text_and_html_can_coexist(self) -> None:
        c = Content(text="plain", html="<p>html</p>")
        assert c.text == "plain"
        assert c.html == "<p>html</p>"

    def test_content_template_pair_can_coexist(self) -> None:
        c = Content(
            text_view="welcome.txt.j2",
            html_view="welcome.html.j2",
            data={"name": "Ada"},
        )
        assert c.text_view == "welcome.txt.j2"
        assert c.html_view == "welcome.html.j2"
        assert c.data == {"name": "Ada"}

    def test_content_requires_at_least_one(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            Content()

    def test_attachment_with_data(self) -> None:
        att = Attachment(data=b"raw", name="file.txt", mime="text/plain")
        assert att.name == "file.txt"
        assert att.data == b"raw"

    def test_attachment_with_path(self) -> None:
        att = Attachment(path="/tmp/file.txt", name="file.txt", mime="text/plain")  # noqa: S108
        assert att.path == "/tmp/file.txt"  # noqa: S108
