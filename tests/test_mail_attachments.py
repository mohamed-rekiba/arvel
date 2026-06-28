"""Mail (doc 16) — Mailable.attach / attach_data add MIME parts to the rendered message."""

from __future__ import annotations

from pathlib import Path

from arvel.mail import Mailable


class Doc(Mailable):
    def build(self) -> Mailable:
        return self.subject("Invoice").html("<p>see attached</p>")


def _attachments(message: object) -> list:
    return list(message.iter_attachments())  # type: ignore[attr-defined]


def test_attach_file_from_disk(tmp_path: Path) -> None:
    f = tmp_path / "invoice.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    message = Doc().attach(str(f)).render()
    parts = _attachments(message)
    assert len(parts) == 1
    assert parts[0].get_filename() == "invoice.pdf"
    assert parts[0].get_content_type() == "application/pdf"
    assert parts[0].get_payload(decode=True) == b"%PDF-1.4 fake"


def test_attach_data_in_memory() -> None:
    message = Doc().attach_data(b"col1,col2\n1,2", "report.csv", mime="text/csv").render()
    parts = _attachments(message)
    assert len(parts) == 1
    assert parts[0].get_filename() == "report.csv"
    assert parts[0].get_content_type() == "text/csv"


def test_custom_name_and_multiple(tmp_path: Path) -> None:
    f = tmp_path / "x.bin"
    f.write_bytes(b"\x00\x01")
    message = (
        Doc().attach(str(f), name="renamed.bin").attach_data(b"hi", "note.txt", mime="text/plain")
    ).render()
    names = {p.get_filename() for p in _attachments(message)}
    assert names == {"renamed.bin", "note.txt"}


def test_no_attachments_still_renders() -> None:
    message = Doc().render()
    assert _attachments(message) == []
    assert message["Subject"] == "Invoice"
