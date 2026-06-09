# SAD-004 — arvel-image

**Work Item**: WI-arvel-001, WI-arvel-002 (consolidated under WI-arvel-003) · **Status**: Approved · **Related**: ADR-020, ADR-132-arvel-image

**Scope**: All architecture-touching decisions for `arvel-image` made during the 1.0 polish pass (WI-arvel-001) and the post-1.0 hardening pass (WI-arvel-002). Consolidated 2026-06-05 during WI-arvel-003.

**Date range**: 2026-06-04 (1.0 polish, WI-arvel-001) → 2026-06-05 (post-1.0 follow-ups, WI-arvel-002) → 2026-06-05 (this consolidation, WI-arvel-003).

> **Adapted artifact.** The schema's `planning-sa` stage canonically produces a full SAD with system design, technology choices, threat model, and OpenAPI spec. The two WIs this document subsumes were both polish/hardening passes on an existing Python library — no greenfield architecture, no OpenAPI (arvel-image is a library, not an HTTP API), no schema changes (beyond the additive `model_id` widening recorded in ADR-020 § 3.5). What this document covers: every architectural decision the package's two 1.x WIs depended on, plus what *doesn't* change.

---

## What does not change (across both WIs)

| Concern | Status | Why |
|---|---|---|
| Public package layout (`arvel_image.*`, `arvel_image.media.*`) | Unchanged | WI-arvel-001 renames affected privacy (`_` prefix) and `__all__` membership, not module structure |
| `Media` SQLAlchemy model | Unchanged | Polymorphic `media` table stays as-is; no columns added or dropped (the `model_id` type was widened in ADR-020 § 3.5 before 1.0 and is stable since) |
| `HasMedia` mixin's contract | Unchanged in shape | `add_image`, `get_media`, `first_media`, `last_media`, `image_url`, `media_in`, `clear_*`, `to_dict` keep their signatures |
| Service provider boot | Unchanged | `ImageServiceProvider` implements only `boot()` (publishes the migration, registers collections from `config.image`) — no `register()` or `shutdown()`; that shape is unchanged |
| Persistence model | Unchanged | Still polymorphic morph-id-as-string, eager-loaded via `.with_("media")` / `.load("media")` |
| Pillow integration | Unchanged | `Image` fluent API and `ConversionRunner` worker-thread offload model stay |
| DB schema | Unchanged in WI-arvel-001 and WI-arvel-002 | See `WI-arvel-001-no-schema-change.md`, `WI-arvel-002-no-schema-change.md`. The 1.0-era `model_id` widening is recorded in ADR-020 § 3.5. |

---

## Part A — WI-arvel-001 1.0 polish pass

Three decisions drove the polish epic's structural changes. Each is recorded in ADR-020 (sections 5, 6, 7).

### A.1 — Public-API rename approach

**Problem.** Before the rename, `arvel_image.__all__` exported more symbols than the package wanted to support — some were internal (e.g., `FileInfo`, helpers re-exported for test convenience). Externally-visible private names = brittle 1.0.

**Approach.** Rename internal symbols with a leading `_` and remove from `__all__`. Cross-package callers (kit, tests) update accordingly. No deprecation shim — `no-backward-compatibility.mdc` permits direct rename.

**Result.** The post-rename public surface is **26** symbols in `arvel_image.__all__` and **22** in `arvel_image.media.__all__`, both pinned by `tests/test_public_surface.py` (`PACKAGE_PUBLIC` / `MEDIA_PUBLIC`).

**Mechanism.** Story 2 in the WI-arvel-001 backlog. Cataloged in **ADR-020 § 5**.

### A.2 — MRO guard on `HasMedia`

**Problem.** `HasMedia.to_dict()` requires `HasMedia` to precede `Model` in the MRO. Wrong order = silent `media` array drop in API responses (an access-control bug shape). Previously documented in the README as "MRO matters" — relies on user discipline.

**Approach.** `HasMedia.__init_subclass__` validates MRO at class definition time, raises `TypeError` with class name + correct order when violated.

**Mechanism.** Story 5. Cataloged in **ADR-020 § 6**.

### A.3 — SSRF guard scope tightening

**Problem.** The URL fetcher (`media/url_fetcher.py`) is the highest-leverage security surface in the package — it takes a caller-supplied URL and fetches it server-side. The guard needed to block requests to internal addresses and stop a server from lying about content type.

**What shipped.** `fetch_url` enforces, in order:

- **Scheme allowlist** — only `http`/`https`; `file://`, `ftp://`, and the rest are rejected with `MediaError`.
- **Private-IP rejection** — `reject_private_ip` resolves the host via `getaddrinfo` and rejects any address that is private, loopback, link-local, multicast, reserved, or unspecified.
- **No redirects** — `follow_redirects=False`, so a redirect to an internal address can't bypass the guard; callers must supply the final URL.
- **Size cap** — streams the body and aborts past `max_bytes`, plus a fail-fast `Content-Length` header check.
- **Opt-in MIME cross-check** — when a caller passes `expected_mime_prefix="image/"`, the bytes are sniffed with Pillow (`sniff_image_mime`) and compared to the server's `Content-Type`; a mismatch raises `InvalidMimeTypeError`.

**Known limitation — DNS rebinding.** The guard resolves the host once, then httpx re-resolves it for the actual request (a TOCTOU window). The module docstring documents this; there is **no** Host/SNI pinning to the validated IP. Callers passing fully attacker-controlled URLs should treat rebinding as a residual risk.

**Mechanism.** Cataloged in **ADR-020 § 7** (refines the original SSRF guard recorded in **ADR-020 § 4**).

### Threat model delta (WI-arvel-001)

| Threat | Pre-WI-arvel-001 | Post-WI-arvel-001 |
|---|---|---|
| SSRF via user-supplied image URL | Mitigated for loopback + RFC1918 private; **gaps**: MIME cross-check missing, DNS rebinding | Scheme allowlist + broadened private-IP reject (private/loopback/link-local/multicast/reserved/unspecified) + `follow_redirects=False` + opt-in MIME bytes-vs-header cross-check. **DNS rebinding is not mitigated — documented as a residual risk.** |
| API consumer reaches into a renamed-private symbol | N/A (currently exported) | Cleanly broken at import — fail loud (acceptable: pre-1.0, no users on PyPI yet) |
| Silent `media` drop from `to_dict()` due to MRO mistake | User-disciplined (documented, not enforced) | `TypeError` at class definition time |

OWASP A01 (Broken Access Control / SSRF), A05 (Injection — scheme allowlist). No new attack surface introduced.

---

## Part B — WI-arvel-002 post-1.0 follow-ups

Two architecture-touching decisions from the post-1.0 hardening bundle. Stories 1 and 2 were pure test additions — no architecture impact, omitted here. Stories 3 and 4 drove the decisions below.

### B.1 — MinIO fixture: copy vs extract (Story 3)

**Context**: The e-commerce kit owns a session-scoped `minio_endpoint` (testcontainers + boto3 bucket bootstrap) and a per-test `minio_bucket` fixture in `kits/arvel-ecommerce-kit/backend/tests/conftest.py`. Story 3 needs the same fixture in `packages/arvel-image/tests/conftest.py` for the `MediaLibrary.regenerate()` integration test.

**Options considered**:

| Option | Pros | Cons |
|---|---|---|
| **A — Extract to `arvel.testing.s3`** (a new module in the framework core) | DRY. One owner. Future packages can reuse. | Adds public surface to `arvel` core. Larger blast radius if the fixture API changes. |
| **B — Extract to `arvel-image` itself** (e.g., `arvel_image.testing.s3`) | Keeps the fixture close to its primary consumer. | Awkward dependency direction — kit would import test-infra from a leaf package. |
| **C — Copy-paste into `arvel-image/tests/conftest.py`** with one-line attribution | Zero new public surface. Lowest blast radius. Each package can evolve its fixture independently. | DRY violation (~30 lines duplicated). |

**Decision**: **Option C** (copy-paste). Promote to Option A if a third caller appears. Per `001-no-overengineering.mdc`'s Rule of Three — one current caller (the kit) plus one new caller (arvel-image tests) is **two**. Bounded duplication, benign drift mode, trivially reversible.

→ Cataloged in **ADR-020 § 8**.

### B.2 — `aiohttp` CVE pin scope (Story 4)

**Context**: `pip-audit` workspace-wide reports `aiohttp 3.13.5` vulnerable to CVE-2026-34993 and CVE-2026-47265, both fixed in 3.14.0. `uv tree --package arvel-image | rg aiohttp` returns zero matches — `aiohttp` is not in `arvel-image`'s dependency tree.

**Options considered**:

| Option | Pros | Cons |
|---|---|---|
| **A — Workspace-level constraint** in root `pyproject.toml` | One pin covers all packages. | Silently binds packages that don't import `aiohttp`. |
| **B — Pin in the owner package's `pyproject.toml`** | Pin lives next to its consumer. Other packages stay unaware. | Requires identifying the owner. |
| **C — Do nothing** (claim "non-prod code path") | Zero churn. | False — both CVEs are in production code paths. |

**Decision**: **Option B**. Owner identified via `uv tree | rg aiohttp -B 5` as the `arvel` core package (`queue` + `s3` extras). Pin lives in `packages/arvel/pyproject.toml`.

→ Cataloged in **ADR-020 § 9**.

### B.3 — `requires_emulator` marker scope (Story 3)

**Decision**: Reuse the existing marker as-is. No new pyproject changes. Document the marker in `packages/arvel-image/README.md` under "Integration tests" so contributors know how to opt in (`pytest -m requires_emulator` or `make test-emulator`).

No ADR — documentation-only.

### Threat model (WI-arvel-002)

| Story | STRIDE category | Threat | Mitigation |
|---|---|---|---|
| 1 (Track E) | none | Pure test additions; no new attack surface. | n/a |
| 2 (Track D) | A05 — Misconfig | A future change might leak credentials in error messages. The `_safe_url` userinfo-stripping branches now have explicit tests pinning the security invariant. | AC explicitly requires "assert the credential **does not appear** in the returned string". |
| 3 (Track F) | A05 — Misconfig (test credentials) | MinIO test credentials (`minioadmin:minioadmin`) might end up in a non-test code path. | Credentials are sourced from `_MINIO_ROOT_USER`/`_MINIO_ROOT_PASSWORD` constants gated by `pytest.fixture` scope. |
| 4 (CVE) | A03 — Supply Chain | The two `aiohttp` CVEs. | Pin to `>=3.14.0` in the owner package. `pip-audit` exit 0 verifies. |

No new threats introduced beyond the ones mitigated above.

---

## Dependencies on other packages

None for either WI. Every change is local to `packages/arvel-image/` (and, for B.2, the owner package's `pyproject.toml`).

## Verification strategy

Standard project gates: `make lint format-check typecheck`, `pytest packages/arvel-image -m 'not benchmark and not requires_emulator' --cov=arvel_image`, `mkdocs build --strict`. Security gate adds: `bandit -r packages/arvel-image/src`, `pip-audit` workspace-wide. Coverage on `arvel-image` ended ≥ 92% after WI-arvel-002 (vs. the 84.49% pre-WI-arvel-001 baseline).

## What this SAD does NOT cover

- **No OpenAPI spec** — `arvel-image` is a Python library, not an HTTP service.
- **No DB schema** — no schema changes in either WI.
- **No new public API** — the public surface is pinned by `tests/test_public_surface.py` (from WI-arvel-001 iter 7) and unchanged by either subsequent WI.

---

## Subsumes

| Old | Date | Work item | New location |
|---|---|---|---|
| SAD-004 — arvel-image 1.0 polish pass | 2026-06-04 | WI-arvel-001 | Part A (this file) |
| SAD-005 — arvel-image post-1.0 follow-ups | 2026-06-05 | WI-arvel-002 | Part B (this file) |

This consolidation happened in WI-arvel-003 (2026-06-05) alongside the seven-into-one ADR merge recorded in `ADR-132-arvel-image.md § Subsumes`. The next free SAD number is **006**.
