# ADR-132 — `arvel-image` driver: Pillow only

**Status**: Accepted
**Date**: 2026-05-20

## Context

Spatie's PHP `spatie/image` v3 supports two backends: GD and ImageMagick. We need an equivalent for Arvel. Python options:

| Driver | Pros | Cons |
|---|---|---|
| **Pillow** | Pure-Python (mostly), PEP 561 stubs in 11.x, ubiquitous, MIT, no shelling out | No AVIF in stock build (needs `pillow-heif`), conservative on advanced filters |
| **ImageMagick via Wand** | Wider format support, faster on some ops | Requires system ImageMagick; CVE-prone history; binding-level memory issues |
| **OpenCV** | Fast, parallel | Wrong tool — designed for CV, not for "make this thumbnail"; large install, AGPL fragments |
| **Vips via pyvips** | Very fast, low memory | C library install; harder onboarding; less ecosystem cohesion |
| **Custom (ffmpeg / libvips CLI)** | Maximum control | Shells out — directly conflicts with NFR-025-07 |

## Decision

**Pillow only at v1.** Single driver. No abstraction layer that allows swapping backends.

Reasons:

1. **Security boundary**: NFR-025-07 forbids shelling out. Pillow processes through Python — no `subprocess`, no path-injection risk in a tempfile dance.
2. **Type completeness**: Pillow 12.x ships PEP-561 stubs. `pyright --strict` and `mypy --strict` pass without `Any` leakage in image code.
3. **Onboarding**: Most Python devs already have Pillow installed. `pip install 'arvel[image]'` succeeds in seconds without OS packages.
4. **Constitution Article II.1** — "Integrate, don't replace." Pillow is the standard async-Python image library. Wrapping it (vs forking or replacing) is the correct play.
5. **Surface coverage**: All operations in PRD-025 §4.3 (resize, crop, fit, format, quality, orient, background, optimize) are first-class in Pillow.

AVIF support: opportunistic. If `pillow-heif` is installed at runtime we accept `.avif`. If not, we raise `UnsupportedFormatError` with a clear "install pillow-heif" message. This is documented in the package README.

## Consequences

✅ Single, well-understood failure surface. CVE response is straightforward (`pip-audit` + `pip install --upgrade`).
✅ No system dependency on libraries that drift across distros.
✅ Strict typing throughout. No abstraction layer = no abstraction tax.

⚠️ Heavy users (high-throughput pipelines) might want Vips later. Documented as a known limitation. If users actually report this, we revisit with a v2 ADR.
⚠️ AVIF / HEIC are second-class. Most apps don't ship those out today; acceptable.
⚠️ Pillow's MAX_IMAGE_PIXELS guard must be set explicitly to defeat decompression-bomb attacks. We set it to 178956970 (~178MP) and let users override via `arvel_image.set_max_pixels(...)`.

## Pillow version pin

`Pillow >= 12.2.0`. Verified via PyPI 2026-05-20: latest stable is 12.2.0; PEP 561 stubs included. Pin in `packages/arvel-image/pyproject.toml`.

## Alternatives considered

- **(A) Backend abstraction** (`Driver` Protocol with PillowDriver, WandDriver) — premature. Rejected per `001-no-overengineering.mdc`. Add only when a second driver is genuinely needed.
- **(B) Fork or wrap a higher-level lib** (`PIL.ImageOps` is already higher-level enough) — no value add.
