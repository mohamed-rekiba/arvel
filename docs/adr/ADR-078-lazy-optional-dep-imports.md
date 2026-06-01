# ADR-078 — Lazy optional-dependency imports in cloud drivers

**Status**: Accepted
**Date**: 2026-05-17
**Deciders**: Arvel core team

---

## Context

`S3Driver`, `GcsDriver`, and `AzureDriver` require `aioboto3`, `google-cloud-storage`, and
`azure-storage-blob` respectively. These are heavy packages. Apps that only use local storage
should not be forced to install them.

The question is: where does the import happen?

## Decision

Cloud driver packages are imported inside `__init__` (not at module level). The import is
wrapped in `try/except ImportError` with a friendly re-raise.

```python
class S3Driver:
    def __init__(self, config: S3Config) -> None:
        try:
            import aioboto3  # noqa: PLC0415
            self._aioboto3 = aioboto3
        except ImportError:
            raise ImportError(
                "S3Driver requires 'arvel[s3]'. "
                "Install with: pip install \"arvel[s3]\""
            ) from None
```

## Rationale

1. **Import safety**: `from arvel.storage import LocalDriver` works with zero extras installed.
2. **Error at use, not at startup**: the error surfaces when the driver is instantiated (i.e.,
   when the developer explicitly asks for it), not during application boot.
3. **Pyright compliance**: `self._aioboto3 = aioboto3` stores the module reference; subsequent
   attribute accesses go through `self._aioboto3`, which pyright treats as `ModuleType`.
   Where necessary, `# pyright: ignore[reportUnknownMemberType]` is used on specific accesses
   since aioboto3 has no type stubs (consistent with WI-005 `shell.py` precedent).
4. **`noqa: PLC0415`**: Ruff's "import not at top of file" rule is suppressed inline at the
   import site. This is the single approved exception for optional-dep guards.

## Consequences

- Apps that miss an extra get a clear, actionable error at driver instantiation.
- The CI extras-matrix job (DX gate 49) verifies each extra installs and imports correctly.
- Every cloud driver `__init__` has a `# pyright: ignore[reportMissingModuleSource]` for the
  `import aioboto3` line (no stubs for optional deps).
