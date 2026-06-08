# Epic: SMTP driver sends path-based attachments

## Summary
The SMTP driver attached only `data` (raw bytes) attachments — a `path`-based `Attachment`
(documented as a first-class option) was silently dropped, so mail went out without the file and
no error was raised. The part also hardcoded `application/octet-stream`, ignoring the attachment's
declared `mime`. The driver now reads `path` from disk, honors `mime`, and rejects an attachment
with neither source.

**Module:** mail · **Spec:** `docs/pipeline/specs/WI-arvel-010-smtp-path-attachments.md`

## Stories

### Story 1: Path-based attachments are actually sent
**As an** application developer, **I want** `Attachment(path=...)` to be read and attached when I
send mail, **so that** the documented path option works instead of silently dropping the file.

**Acceptance Criteria**:
- [x] Given a mailable with a `path`-only attachment, when sent via SMTP, then the file is read from disk and attached with its bytes.
- [x] Given an attachment with a declared `mime`, when attached, then the MIME part's `Content-Type` matches that `mime` (not hardcoded octet-stream).
- [x] Given an attachment with neither `path` nor `data`, when building the message, then it raises `MailException` instead of silently producing an empty part.

**Security Requirements**:
- [x] Filename is set via `add_header(..., filename=)` (RFC 2231 encoding) rather than raw interpolation into the header.

**Documentation Requirements**:
- [x] `docs/site/docs/features/mail.md` notes that the SMTP driver reads `path`, sets `Content-Type` from `mime`, and requires one of `path`/`data`.

**Requirement Refs**: SPEC-1, SPEC-2, SPEC-3
**Priority**: Must · **Complexity**: Small · **Status**: Done

### Story 2: Existing data attachments and integration sends keep working
**As an** application developer, **I want** `data` attachments and live SMTP delivery to behave as
before, **so that** the path fix is purely additive.

**Acceptance Criteria**:
- [x] Given a `data` attachment, when sent, then it's attached as before.
- [x] Given the Mailpit integration path, when a mail with an attachment is sent, then delivery and filenames are unchanged.

**Security Requirements**:
- [x] None.

**Documentation Requirements**:
- [x] Covered by the attachments doc section.

**Requirement Refs**: SPEC-4
**Priority**: Must · **Complexity**: Small · **Status**: Done

## Dependencies
- None. Independent of WI-arvel-001..009.

## Notes
- The kit defines no mailables; all mail is auth (`VerifyEmailMailable`, `PasswordResetMailable`),
  neither of which uses attachments today — so this is a framework-correctness fix.
- Cleared as a non-defect: suspected CRLF SMTP header injection — Python's `email` generator raises
  `HeaderParseError` on embedded newlines, so the stdlib already blocks it.
- Deferred follow-ups (separate work items):
  - **C2** — sync Jinja2 render in the async send path (wrap in a thread).
  - **H1** — `Mailer.to(obj)` without `.email` becomes `str(obj)` instead of failing.
  - **H3** — provider config failure silently falls back to the log driver.
  - **H4** — template/render errors escape as Jinja2 exceptions, not `MailException`.
  - **Parity-additive** — fluent cc/bcc/replyTo, multiple recipients, queued mailables,
    `Mail.assertSent*`, markdown mail, embedded images, custom headers, `tags`.
  - **Kit gap** — auth email templates not published into the kit's `view.paths`.
