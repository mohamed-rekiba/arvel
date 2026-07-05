"""Mail (spec 19) — a Mailable with only an HTML body still sends multipart/alternative with a
text/plain part (deliverability); ``text()`` overrides the auto-derived alternative."""

from __future__ import annotations

from arvel.mail import Mailable


class HtmlOnly(Mailable):
    def build(self) -> Mailable:
        return self.subject("Receipt").html("<p>Thanks for your <strong>order</strong>!</p>")


class ExplicitText(Mailable):
    def build(self) -> Mailable:
        return self.subject("Receipt").html("<p>rich</p>").text("plain override")


def test_html_only_mailable_sends_multipart_alternative_with_a_text_part() -> None:
    message = HtmlOnly().render()
    assert message.get_content_type() == "multipart/alternative"
    parts = {p.get_content_type() for p in message.iter_parts()}
    assert parts == {"text/plain", "text/html"}


def test_text_part_is_auto_derived_by_stripping_html_tags() -> None:
    message = HtmlOnly().render()
    body = message.get_body(preferencelist=("plain",))
    assert body is not None
    text = body.get_content()
    assert text.strip() == "Thanks for your order!"
    assert "<" not in text


def test_explicit_text_overrides_the_auto_derived_alternative() -> None:
    message = ExplicitText().render()
    body = message.get_body(preferencelist=("plain",))
    assert body is not None
    assert body.get_content().strip() == "plain override"


def test_html_part_is_unchanged() -> None:
    message = HtmlOnly().render()
    body = message.get_body(preferencelist=("html",))
    assert body is not None
    assert body.get_content().strip() == "<p>Thanks for your <strong>order</strong>!</p>"


def test_attachments_still_ride_alongside_the_alternative_parts(tmp_path: object) -> None:
    from pathlib import Path

    class WithAttachment(Mailable):
        def build(self) -> Mailable:
            return self.subject("Invoice").html("<p>see attached</p>")

    f = Path(str(tmp_path)) / "invoice.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    message = WithAttachment().attach(str(f)).render()
    assert message.get_content_type() == "multipart/mixed"
    assert [a.get_filename() for a in message.iter_attachments()] == ["invoice.pdf"]
    body = message.get_body(preferencelist=("html",))
    assert body is not None
    assert body.get_content().strip() == "<p>see attached</p>"
