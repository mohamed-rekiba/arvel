# WI-arvel-010 — SMTP driver must send path-based attachments (and honor mime)

| | |
|---|---|
| **Module** | mail |
| **Complexity** | L2 | **Risk** | Tier 2 | **Data** | internal |
| **Autonomous** | yes | **Frontend** | no |
| **Research** | `.context/research/010-mail.md` (C1 fixed; C3 cleared as false positive; C2/H/M deferred) |
| **Review** | C1 confirmed: documented `path` attachments silently dropped on the only real transport |

## Problem

`SmtpMailDriver._build_message` attached only `att.data`:

```python
for att in mail.attachments:
    if att.data is not None:        # path-only attachments silently dropped
        part = MIMEBase("application", "octet-stream")   # att.mime ignored
        part.set_payload(att.data)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{att.name}"')
        msg.attach(part)
```

`Attachment` and the docs document `path` (file on disk) as a first-class option
("Provide either `path` … or `data`"). On the only real transport (SMTP), a
`path`-only attachment was silently dropped — the mail sent without it, no error.
The part also hardcoded `application/octet-stream` (ignoring `att.mime`) and
interpolated `att.name` raw into the `Content-Disposition` header.

## Spec Items → Verification

| ID | Spec item | Test | Status |
|---|---|---|---|
| SPEC-1 | A `path`-only attachment is read from disk and attached with its bytes. | `tests/test_mail/drivers/test_smtp_driver.py::TestSmtpDriver::test_path_attachment_is_read_and_attached` | PASS |
| SPEC-2 | The attachment part's `Content-Type` comes from `att.mime` (not hardcoded octet-stream). | same test (`get_content_type() == "application/pdf"`) | PASS |
| SPEC-3 | An attachment with neither `path` nor `data` raises `MailException`. | `...::test_attachment_without_path_or_data_raises` | PASS |
| SPEC-4 | `data` attachments and the Mailpit integration path still work. | existing `test_array_driver`/`test_mailer`/`test_smtp_driver_integration` | PASS |
| SPEC-5 (X-cut: types/lint) | mypy `--strict` + pyright clean; ruff clean on changed files; mail suite green (48). | `mypy` + `pyright` + `ruff` + `pytest` | PASS |

## Root-cause fix

`drivers/smtp.py` — extracted `_build_attachment(att)`:
- resolve bytes from `att.path` (`Path(att.path).read_bytes()`) when `att.data`
  is None; raise `MailException` if neither is set;
- split `att.mime` into maintype/subtype for `MIMEBase` (default
  `application/octet-stream`);
- set the filename via `add_header("Content-Disposition", "attachment",
  filename=att.name)` — RFC 2231 encoding handles quotes / non-ASCII safely.

## Deliberate design decisions

- **Read `path` synchronously** inside the already-sync `_build_message`.
  Attachments are typically small, and the broader "render in a thread" change
  (C2) is deferred — keeping this fix surgical.
- **Fail loud on an empty attachment** (no `path`/`data`) rather than silently
  skipping — surfaces a misconfigured mailable.

## Cleared (not a defect)

- **C3 (CRLF header injection)** — false positive. Python's `email` generator
  raises `HeaderParseError` when serializing a header that contains an embedded
  newline, so the stdlib already blocks SMTP header injection. (The error type
  isn't `MailException` — a minor error-contract nit, deferred.)

## Deferred (tracked)

- **C2** — sync Jinja2 render + `html_to_text` in the async send path (wrap in
  `anyio.to_thread`).
- **H1** — `Mailer.to(obj)` without `.email` becomes `str(obj)` instead of failing.
- **H3** — provider config failure silently falls back to env/log driver.
- **H4** — template/render errors escape as Jinja2 exceptions, not `MailException`.
- **Parity-additive** — fluent `cc`/`bcc`/`replyTo`, multiple recipients, queued
  mailables, `Mail.assertSent*`, markdown mail, embedded images, custom headers,
  `tags` application.
- **Kit gap** — auth email templates not published into the kit's `view.paths`
  (would `TemplateNotFound` on a real send); kit config/publish issue.
