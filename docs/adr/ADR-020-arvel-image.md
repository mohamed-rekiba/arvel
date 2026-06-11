# ADR-020 — `arvel-image`

**Status**: Accepted
**Date**: 2026-05-20 (first decision); last revised 2026-06-05 during the WI-arvel-003 consolidation pass
**Last reconciled**: 2026-06-07 (WI-arvel-005 renumbered ADR-132 → ADR-020)
**Scope**: All architectural decisions for the `arvel-image` package — driver, scope, runtime, security, 1.0 polish, test fixtures, and CVE remediation.

## Why this is one ADR

`arvel-image` accumulated seven ADRs between WI-arvel-025 and WI-arvel-002. Each one made sense in flight, but reading the package's design end-to-end forced opening seven files and chasing cross-references. Per `001-no-overengineering.mdc` and `no-backward-compatibility.mdc` (and the user's explicit choice during the WI-arvel-003 brainstorm), the package's full architecture lives here in nine `§` sections. The originals are listed in `## Subsumes` at the bottom.

---

## § 1 — Driver: Pillow only

**Originally**: ADR-020 (Date: 2026-05-20)

### Context

We need a fluent image-transform layer for Arvel — resize, crop, convert format, set quality, orient, optimise — that fits inside async request handlers without shelling out. Python options:

| Driver | Pros | Cons |
|---|---|---|
| **Pillow** | Pure-Python (mostly), PEP 561 stubs in 11.x, ubiquitous, MIT, no shelling out | No AVIF in stock build (needs `pillow-heif`), conservative on advanced filters |
| **ImageMagick via Wand** | Wider format support, faster on some ops | Requires system ImageMagick; CVE-prone history; binding-level memory issues |
| **OpenCV** | Fast, parallel | Wrong tool — designed for CV, not for "make this thumbnail"; large install, AGPL fragments |
| **Vips via pyvips** | Very fast, low memory | C library install; harder onboarding; less ecosystem cohesion |
| **Custom (ffmpeg / libvips CLI)** | Maximum control | Shells out — directly conflicts with NFR-025-07 |

### Decision

**Pillow only at v1.** Single driver. No abstraction layer that allows swapping backends.

Reasons:

1. **Security boundary**: NFR-025-07 forbids shelling out. Pillow processes through Python — no `subprocess`, no path-injection risk in a tempfile dance.
2. **Type completeness**: Pillow 12.x ships PEP-561 stubs. `pyright --strict` and `mypy --strict` pass without `Any` leakage in image code.
3. **Onboarding**: Most Python devs already have Pillow installed. `pip install 'arvel[image]'` succeeds in seconds without OS packages.
4. **Constitution Article II.1** — "Integrate, don't replace." Pillow is the standard async-Python image library. Wrapping it (vs forking or replacing) is the correct play.
5. **Surface coverage**: All operations in PRD-025 §4.3 (resize, crop, fit, format, quality, orient, background, optimize) are first-class in Pillow.

AVIF support: opportunistic. If `pillow-heif` is installed at runtime we accept `.avif`. If not, we raise `UnsupportedFormatError` with a clear "install pillow-heif" message.

### Consequences

✅ Single, well-understood failure surface. CVE response is straightforward (`pip-audit` + `pip install --upgrade`).
✅ No system dependency on libraries that drift across distros.
✅ Strict typing throughout. No abstraction layer = no abstraction tax.

⚠️ Heavy users (high-throughput pipelines) might want Vips later. Documented as a known limitation.
⚠️ AVIF / HEIC are second-class. Most apps don't ship those out today; acceptable.
⚠️ Pillow's `MAX_IMAGE_PIXELS` guard must be set explicitly to defeat decompression-bomb attacks. We set it to 178956970 (~178MP) and let users override via `arvel_image.set_max_pixels(...)`.

### Pillow version pin

`Pillow >= 12.2.0`. Verified via PyPI 2026-05-20: latest stable is 12.2.0; PEP 561 stubs included. Pin in `packages/arvel-image/pyproject.toml`.

### Alternatives considered

- **(A) Backend abstraction** (`Driver` Protocol with PillowDriver, WandDriver) — premature. Rejected per `001-no-overengineering.mdc`.
- **(B) Fork or wrap a higher-level lib** (`PIL.ImageOps` is already higher-level enough) — no value add.

---

## § 2 — Scope: ship the media-library layer in the same package

**Originally**: ADR-021 (Date: 2026-05-21). Amends § 1.

### Context

When § 1 landed, `arvel-image` was framed as a stateless Pillow wrapper — "transform these bytes". That misses the much more common application workflow: *"attach this file to my model, generate thumbnails, give me a URL back."* That second workflow needs a polymorphic `media` table, a `HasMedia` trait on host models, conversion generation, disk routing, and a `MediaLibrary` service.

Splitting transforms and media-library across two packages (`arvel-image` for transforms, a hypothetical `arvel-medialibrary` for the model association) gives us two PyPI extras with overlapping deps, two READMEs, two `vendor:publish` tags. One "image stuff lives here" package is closer to what consumers expect.

### Decision

`arvel-image` ships **both** layers:

1. The fluent transform API (`arvel_image.Image`, § 1 — unchanged).
2. A polymorphic `media` table plus `ImageServiceProvider` that registers it as publishable under tag `arvel-image`.

The `media` table schema: id, polymorphic `model_type` / `model_id`, `uuid`, `collection_name`, `name`, `file_name`, `mime_type`, `disk`, `conversions_disk`, unsigned `size`, JSON columns for `manipulations` / `custom_properties` / `generated_conversions` / `responsive_images`, indexed nullable `order_column`, nullable timestamps.

Apps that only want the transform API still get a clean install: `from arvel_image import Image` works without booting a provider. The migration only lands in `database/migrations/` if the app explicitly runs `arvel vendor:publish --tag=arvel-image`.

### Consequences

✅ One package, one extras flag, one README.
✅ § 1's Pillow-only constraint is unchanged — the transform code paths still don't shell out, still have full PEP-561 typing.
✅ The migration is opt-in. Apps that don't need the `media` table pay zero cost.

⚠️ `arvel-image` now depends on `arvel` (it imports `ServiceProvider`). Documented in the README.
⚠️ "I want the model association but not the transforms" is not a supported configuration. Acceptable: the transform code is small (~180 lines, Pillow-only), and Pillow is already in most Python images.

### Alternatives considered

- **(A) Keep `arvel-image` stateless; ship a separate `arvel-medialibrary`.** Rejected: doubles the surface area consumers have to discover.
- **(B) Bake the runtime layer in the same WI as the migration.** Rejected per `001-no-overengineering`: the runtime layer's shape (sync vs async, eager vs lazy) deserves a dedicated design pass — see § 3.

---

## § 3 — Runtime layer: sync conversions, short-class polymorphism, default path scheme

**Originally**: ADR-022 (Date: 2026-05-20), including two later merged sub-decisions (2026-05-24) on `HasMedia` aliases and `Media.model_id` type. Depends on § 1, § 2.

### Context

§ 2 chose to ship the full media-library layer inside `arvel-image` but shipped only the `media` table as a publishable migration. The runtime layer (the `Media` ORM model, the `HasMedia` trait, and the conversion engine) was deferred. § 3 lands that layer. Three architectural calls deserve a record:

1. **Sync vs queued conversions.** Should `attach_media(...)` block on the conversion or hand it off to `arvel.queue`? Queueing pulls a transitive dep on `arvel.queue` for a behaviour that 80% of consumers won't see (single-file uploads, one or two conversions, a few hundred ms total).
2. **Polymorphic discriminator value.** The `media` table's `model_type` column can store either the unqualified class name (`"User"`) or the fully-qualified name (`"app.models.User"`). Arvel's existing `MorphOne` / `MorphMany` use the unqualified name (ADR-008 § 4).
3. **Default path scheme.** What URL layout does `attach_media` produce on the disk?

### Decision

**3.1 Sync conversions only in v1.** `ConversionRunner.run` executes synchronously inside `FileAdder.to_media_collection`, before that coroutine returns. Pillow's CPU work is wrapped in `anyio.to_thread.run_sync` to avoid blocking the event loop. There is no `.queued()` / `.non_queued()` toggle at v1.

**3.2 Short class name as polymorphic discriminator.** `Media.model_type` stores `type(host).__name__` — the unqualified class name. Same convention as `MorphOne` / `MorphMany` per ADR-008 § 4. The trait can therefore reuse `MorphMany(Media, name="model")` directly.

**3.3 Default path scheme: id-partitioned.** `DefaultPathGenerator`:
- Original: `{media.id}/{file_name}`
- Conversion: `{media.id}/conversions/{name}-{file_name}`

This is the same layout the broader PHP ecosystem standardised on for polymorphic media tables, so URL handlers ported from PHP-shaped apps keep working.

**3.4 `HasMedia` aliases and `HasMediaMixin` re-export.** Add `attach_media(source, *, file_name, collection)` as a one-call alias chaining `add_media().to_media_collection(collection)`. Add `delete_media(collection)` as an alias for `clear_media_collection(collection)`. Export `HasMediaMixin = HasMedia` from `arvel_image/__init__.py`.

**3.5 `media.model_id` type.** `String(36)` — defined directly in `create_media_table.py` (`t.string("model_id", length=36)`), so there's no separate alter migration to publish. `HasMedia.host_pk()` returns `str(self.id)` so integer PKs store as `"1"`, `"2"`, still unique and filterable. This supports UUID-PK host models (e.g., the e-commerce kit's `Product` uses `uuid4()` PKs); INTEGER would silently truncate.

### Consequences

✅ Sync conversions keep the package stand-alone — apps that don't use `arvel.queue` still get the full media-library API.
✅ Short-class polymorphism lets the trait reuse the existing `MorphMany` accessor.
✅ Default path scheme is `{media.id}/...` — apps porting from PHP-shaped media tables don't have to rewrite their URL handlers.
✅ `attach_media` is more ergonomic — single call vs. `add_media().to_media_collection()` chain.
✅ `model_id: String(36)` supports UUID-PK host models without breaking integer-PK hosts.

⚠️ Sync conversions mean a slow Pillow operation can extend a request handler's latency. Mitigated by `anyio.to_thread.run_sync`.
⚠️ `model_id` widens from 8 bytes (BIGINT) to 36 bytes (VARCHAR) — negligible at typical scales. ORM users unaffected; raw-SQL queries that joined on integer `model_id` must cast.

### Alternatives considered

- **(A) Queued conversions via arvel.queue.** Rejected — pulls `arvel.queue` into `arvel-image`'s critical path.
- **(B) FQN polymorphic discriminator.** Rejected — would require parallel infrastructure to ADR-008 § 4 just for one feature.
- **(C) Date-prefixed path scheme** (`{yyyy}/{mm}/{id}/{file_name}`). Rejected for the default. Consumers who want partitioning bind their own `PathGenerator`.
- **(D) Async dispatch in v1 with a `.queued()` opt-in.** Rejected per `001-no-overengineering.mdc` — no concrete consumer asking for it.

> **Note**: § 3 was authored as a single ADR but, mid-flight, two pragmatic sub-decisions (3.4 `HasMedia` aliases, 3.5 `model_id` type) were appended to it. They are preserved verbatim above.

---

## § 4 — SSRF guard via stdlib `ipaddress`

**Originally**: ADR-135 (Date: 2026-05-24). Extended by § 7 (DNS rebinding mitigation and MIME cross-check).

### Context

`add_media_from_url()` downloads a file from an arbitrary caller-supplied URL. Without a guard an attacker could supply `http://169.254.169.254/latest/meta-data/` (AWS IMDSv1), `http://127.0.0.1:5432/`, or similar to exfiltrate internal services.

### Decision

Before opening the httpx connection, resolve the hostname with `socket.getaddrinfo()` and check each returned IP against Python's `ipaddress` stdlib. Reject addresses where any of the following holds:

- `ip.is_private`
- `ip.is_loopback`
- `ip.is_link_local`
- `ip.is_multicast`
- `ip.is_reserved`

If any IP in the resolved set is rejected, raise `MediaError("SSRF guard blocked <hostname>")`.

### Alternatives considered

1. **Block list via regex on the URL** — rejected; easy to bypass with URL encoding or redirects.
2. **`httpx` event hook on connect** — more complex; requires parsing `httpx` internals.
3. **External DNS resolver library** — avoids DNS rebinding but adds a dependency; deferred.

### Limitations

DNS rebinding attacks (time-of-check to time-of-use) bypass this guard. Documented in the `add_media_from_url()` docstring. A TOCTOU-safe guard requires connecting through a controlled proxy or using `httpx` CONNECT-level hooks — **see § 7 for the closure of that gap** during the WI-arvel-001 polish pass.

### Consequences

- ✅ Blocks the most common SSRF patterns (metadata services, internal APIs).
- ✅ No external dependencies; stdlib only.
- ⚠️ DNS rebinding initially still possible (closed in § 7).

---

## § 5 — 1.0 polish: public-API rename approach (leading underscore + `__all__` curation)

**Originally**: ADR-138 § 1 (Date: 2026-06-04). Work Item WI-arvel-001.

### Context

`arvel_image.__all__` exported 31 symbols; `arvel_image.media.__all__` exported 29. Several were framework internals re-exported only because tests or the kit reached for them in early iterations: `FileInfo`, `CollectionConfig`, `ConversionConfig`, `get_collection_preset`, `register_collection_preset`, `get_conversion_runner`, `set_conversion_runner`, `get_path_generator`, `set_path_generator`, `MediaLibrary`, `copy_responsive_images`, `generate_responsive_images_for_media`, `calculate_responsive_widths`, `generate_placeholder_svg`. Each export becomes a 1.0 stability commitment.

### Options considered

| Option | Pro | Con |
|---|---|---|
| **(A)** Leave `__all__` as-is | Zero churn | Commits us to 31 symbols at 1.0; many internals locked in |
| **(B)** Rename internals with `_` prefix, drop from `__all__` | Smallest public surface; cleanest 1.0 commitment | Breaks anyone importing internals (acceptable — pre-alpha, no PyPI users) |
| **(C)** Add a separate `arvel_image._internal` namespace | Explicit separation | Two-namespace ceremony for limited gain on a 34-file package |
| **(D)** Deprecate then remove over two releases | Standard library practice | Banned by `no-backward-compatibility.mdc` |

### Decision

**Option (B)**. Rename internal symbols with a leading `_` (e.g., `_FileInfo`, `_CollectionConfig`), remove from both `__all__` lists. Update kit + framework callers that reach internals in the same WI.

### Consequences

- App-developer-facing imports unchanged for the surface listed in the README's quick-start.
- Any direct import of `FileInfo` / `MediaLibrary` / `*_responsive_images` / etc. breaks at import time. **Loud failure is the goal**.
- Future additions to `__all__` are now meaningful — a deliberate commitment, not historical accident.

---

## § 6 — 1.0 polish: MRO guard on `HasMedia` via `__init_subclass__`

**Originally**: ADR-138 § 2 (Date: 2026-06-04). Work Item WI-arvel-001.

### Context

`HasMedia.to_dict()` calls `super().to_dict()` to chain into `Model.to_dict()`, then appends a serialized `media` array. If a host class inherits `(Model, HasMedia, Timestamps)` (wrong order) instead of `(HasMedia, Model, Timestamps)` (correct order), `super()` resolution skips `HasMedia.to_dict()` entirely — the `media` array silently disappears from API responses. Today this is mitigated by an admonition in the README.

A silent missing-data bug in an API response is the shape of an OWASP A01 (Broken Access Control) finding — even if the data being dropped is the user's own. User-discipline-as-control is the weakest mitigation possible.

### Decision

`HasMedia.__init_subclass__(cls, **kwargs)` walks `cls.__mro__`, finds the indices of `HasMedia` and `Model`, raises `TypeError` if `Model` precedes `HasMedia`. Message names the class and the correct inheritance order.

### Consequences

- Wrong MRO fails at class-definition time — discovered by the first test that imports the model.
- Adds ~10 lines to `HasMedia`.
- The README's "MRO matters" admonition reduces to one line: "The framework enforces this for you — if you get the order wrong, the class fails to define."

---

## § 7 — 1.0 polish: SSRF hardening (DNS rebinding + MIME cross-check)

**Originally**: ADR-138 § 3 (Date: 2026-06-04, with a correction note). Work Item WI-arvel-001. Refines § 4.

> **Correction note** (preserved from the original). The original draft of this section was written from spec memory and overstated the gaps. After reading `packages/arvel-image/src/arvel_image/media/url_fetcher.py` directly during QA-Pre setup, the actual gaps are narrower than initially claimed. This section now reflects the true state of the code.

### Actual state of the existing guard

`url_fetcher.py` (~110 lines) already implements most of what a hardened SSRF guard needs, using `ipaddress` stdlib's classification properties on every IP returned by `socket.getaddrinfo()`:

```python
_SSRF_REJECT = ("is_private", "is_loopback", "is_link_local",
                "is_multicast", "is_reserved", "is_unspecified")
```

| Threat | Status in current code | Notes |
|---|---|---|
| Loopback (`127/8`, `::1`) | ✅ Blocked | `is_loopback` |
| RFC1918 private (`10/8`, `172.16/12`, `192.168/16`) | ✅ Blocked | `is_private` |
| **Link-local incl. AWS metadata `169.254.169.254`** | ✅ Blocked | `is_link_local` covers all of `169.254/16` |
| IPv6 link-local (`fe80::/10`) | ✅ Blocked | `is_link_local` |
| IPv6 ULA (`fc00::/7`) | ✅ Blocked | `is_private` |
| Multicast (`224/4`, `ff00::/8`) | ✅ Blocked | `is_multicast` |
| Reserved / unspecified (`0/8`, `240/4`) | ✅ Blocked | `is_reserved`, `is_unspecified` |
| Streaming size cap (don't OOM on lying Content-Length) | ✅ Implemented | url_fetcher.py |
| Content-Length pre-check | ✅ Implemented | `_reject_oversize_header` |
| Non-`http(s)` schemes | ✅ Blocked | Scheme allowlist |
| Redirect to private IP | ✅ Avoided | `follow_redirects=False` |

### Genuine remaining gaps

Only two concerns were unaddressed:

1. **DNS rebinding**: The module docstring acknowledges this — `_reject_private_ip` resolves the host once, then `httpx` re-resolves it inside `client.stream(...)`. Between the two resolutions, an attacker controlling the authoritative DNS server can return a public IP for the validation lookup and a private IP for the actual connection.

2. **MIME cross-check**: When a collection declares `accept_mime_types([...])`, the current code trusts the `Content-Type` header. A `Content-Type: image/jpeg` response containing arbitrary bytes passes the MIME filter.

### Decision

Close both gaps with bounded, well-tested implementation. TLS SNI override (`httpx.AsyncHTTPTransport` constructor) handles the certificate-vs-IP mismatch. MIME sniff uses Pillow's `Image.open(BytesIO(first_512)).format` for image bytes (since this is the arvel-**image** package, image-format detection is the relevant cross-check; non-image MIME types fall through to the existing header check).

### Consequences

- ~25-40 lines added to `url_fetcher.py`.
- Public API of `fetch_url` unchanged.
- No new external dependency.
- Two new ACs in WI-arvel-001 Story 7: DNS-rebinding-resistant connect, MIME-sniff-cross-check.

---

## § 8 — MinIO test fixture: copy into `arvel-image/tests`, not extract

**Originally**: ADR-139 (Date: 2026-06-04). Work Item WI-arvel-002, Story 3.

### Context

The e-commerce kit (`kits/arvel-ecommerce-kit/backend/tests/conftest.py`) owns a session-scoped `minio_endpoint` fixture (testcontainers + boto3 bucket bootstrap) and a per-test `minio_bucket` fixture. WI-arvel-002 Story 3 needs the same fixture pair in `packages/arvel-image/tests/conftest.py` for a new `MediaLibrary.regenerate()` integration test marked `requires_emulator`.

The fixture is ~30 lines (image pin, container start, boto3 client, bucket create, teardown).

### Decision

Copy the fixture into `packages/arvel-image/tests/conftest.py` with a one-line attribution comment pointing at the kit's version. Do **not** extract to a shared module yet.

### Rationale

- **Rule of Three** (per `100-coding-standards.mdc`): kit + arvel-image = two callers. Extraction at two callers is premature.
- **Bounded duplication**: ~30 lines, single function pair, well-commented in both locations.
- **Benign drift mode**: If the MinIO image versions drift between the two `conftest.py` files, the failure surface is "test runs against different image tags" — not a production correctness issue.
- **Reversibility**: When a third caller appears (or the fixture grows), extract to `arvel.testing.s3` in a follow-up WI. The current API is already extraction-ready.

### Alternatives considered

| Alternative | Why rejected |
|---|---|
| Extract to `arvel.testing.s3` now | Premature abstraction at two callers. |
| Extract to `arvel_image.testing.s3` | Awkward dependency direction — kit would import test infrastructure from a leaf package. |

### Consequences

- One ~30-line block of duplication between kit and arvel-image test fixtures.
- A follow-up WI will be needed if a third caller appears or the fixture grows. Tracked via a TODO comment in both fixture files.

---

## § 9 — `aiohttp` CVE pin: scope to the owner package, not the workspace root

**Originally**: ADR-140 (Date: 2026-06-04). Work Item WI-arvel-002, Story 4.

### Context

`pip-audit` workspace-wide reported `aiohttp 3.13.5` vulnerable to CVE-2026-34993 and CVE-2026-47265, both fixed in 3.14.0. `uv tree --package arvel-image | rg aiohttp` returns zero matches — `aiohttp` is not in `arvel-image`'s dependency tree. The owner is the `arvel` core package via its `queue` and `s3` extras.

### Decision

Pin `aiohttp >= 3.14.0` (or the verified-upstream fix version) in the **owner package's** `pyproject.toml`, not in the workspace root. If multiple packages pull `aiohttp`, each gets its own pin.

### Rationale

- **Ownership clarity**: A workspace-root constraint silently binds packages that don't import `aiohttp`. Owner-scoped pinning keeps the dependency relationship explicit.
- **Locality of change**: When someone reads `arvel/pyproject.toml`, they see the security pin and the reason in one place.
- **Reversibility**: Pin lives next to its dependency. Bumping (or unpinning when the constraint is no longer needed) is a single-file edit.

### Alternatives considered

| Alternative | Why rejected |
|---|---|
| Workspace-level constraint (`tool.uv.constraint-dependencies`) | Silently binds packages that don't import `aiohttp`. Hides ownership. |
| Do nothing (claim "non-prod code path") | False — both CVEs affect `aiohttp`'s production HTTP/WebSocket code. |

### Verification

`uv run pip-audit` workspace-wide returns 0 vulnerabilities after the pin. Owner package's own `pytest` suite remains green.

---

## Cross-cutting summary

- Test count up materially after the WI-arvel-001 polish (Stories 7, 8, 9, 10, 11 were all new tests) and again after WI-arvel-002 (Stories 1-4 added coverage and integration tests).
- Coverage on `arvel-image` ≥ 90% (WI-arvel-001 target met; WI-arvel-002 raised hot paths further — `responsive_image_generator.py` 78% → 92%, `url_fetcher.py` 89% → 100%).
- Three small additions to public docs: SSRF guard section, MRO enforcement mention, errors-reference table.
- Zero new external dependencies introduced by the polish or hardening passes.
- Zero schema changes after the v1 `media` table landed in § 2 (and the additive `model_id` widening in § 3.5).

---

## Subsumes

This single ADR absorbs the following ADRs from the WI-arvel-003 consolidation pass (2026-06-05). The original files are deleted; their decision text is preserved verbatim above in the corresponding `§` sections.

| Old | Date | Subject | New location |
|---|---|---|---|
| ADR-132 | 2026-05-20 | `arvel-image` driver: Pillow only | § 1 (this file) |
| ADR-133 | 2026-05-21 | `arvel-image` scope: laravel-medialibrary parity | § 2 |
| ADR-134 | 2026-05-20 | `arvel-image` runtime: sync conversions, short-class polymorphism | § 3 (incl. 3.4 `HasMedia` aliases, 3.5 `model_id` type) |
| ADR-135 | 2026-05-24 | SSRF Guard via stdlib `ipaddress` | § 4 (extended by § 7) |
| ADR-138 | 2026-06-04 | arvel-image 1.0 polish — three design decisions | § 5, § 6, § 7 |
| ADR-139 | 2026-06-04 | MinIO test fixture: copy vs extract | § 8 |
| ADR-140 | 2026-06-04 | `aiohttp` CVE pin scope | § 9 |

The compact-renumber pass in the same WI moved framework ADRs 136 → 133 and 137 → 134 to close the gap left by these deletions; the next free ADR number is **135**.
