"""Read-model policy for materialized-view backed visibility boundaries.

Closes GAP-002 from ``.context/extras/framework-gaps.md``.

The policy enforces that storefront code goes through a read model (e.g.
``PublishedProduct``) and never queries the write-side model (e.g. ``Product``)
directly. Violations are detected at query construction time, not in
post-hoc source-inspection tests.

Typical test usage::

    from arvel.database.policy import ReadModelPolicy

    policy = ReadModelPolicy(read_model=PublishedProduct, write_model=Product)

    async def test_cart_uses_published_boundary(async_session):
    with policy.guard():
        with pytest.raises(ReadModelPolicyViolationError):
            await Product.find(some_id)           # blocked
            await PublishedProduct.find(some_id)      # allowed

    # Outside the guard the model works normally again.

See also: ``ViewModel`` / ``ReadOnlyModelError`` — the write-mutation guard.
``ImmutableReadModelError`` is an alias for ``ReadOnlyModelError`` for
callers who prefer the read-model terminology.
"""

from __future__ import annotations

import contextlib
from collections.abc import Generator
from typing import Any

from arvel.database.exceptions import ORMError, ReadOnlyModelError

# Semantic alias — callers in read-model contexts can import either name.
ImmutableReadModelError = ReadOnlyModelError


class ReadModelPolicyViolationError(ORMError):
    """Raised when code queries a write-side model while a ``ReadModelPolicy`` guard is active.

    Indicates that the caller bypassed the read-model boundary declared by the
    active :class:`ReadModelPolicy`. Use ``PublishedProduct`` (or whatever read
    model is configured) instead.
    """

    def __init__(self, write_model_name: str, read_model_name: str) -> None:
        super().__init__(
            f"Direct query on {write_model_name!r} is blocked by a ReadModelPolicy. "
            f"Use {read_model_name!r} for read access in this context."
        )
        self.write_model_name = write_model_name
        self.read_model_name = read_model_name


class ReadModelPolicy:
    """Associates a write model with its authoritative read model and provides
    a runtime guard that raises on any direct query of the write model.

    This is primarily a test-time tool — production code should use the read
    model by convention, enforced by these tests.

    Usage::

        policy = ReadModelPolicy(
            read_model=PublishedProduct,
            write_model=Product,
        )

        with policy.guard():
            await Product.find(pk)            # raises ReadModelPolicyViolationError
            await PublishedProduct.find(pk)   # fine

    Thread/task safety: the guard installs a global scope on the write model's
    class, which is process-global state. Don't run guarded tests in parallel
    against the same model class.
    """

    _SCOPE_PREFIX = "_arvel_read_model_policy_"

    def __init__(self, *, read_model: type[Any], write_model: type[Any]) -> None:
        self.read_model = read_model
        self.write_model = write_model

    @contextlib.contextmanager
    def guard(self) -> Generator[ReadModelPolicy]:
        """Context manager that blocks direct queries to :attr:`write_model`."""
        scope_name = f"{self._SCOPE_PREFIX}{id(self)}"
        write_name = self.write_model.__name__
        read_name = self.read_model.__name__

        def _blocking_scope(qb: Any) -> Any:
            raise ReadModelPolicyViolationError(write_name, read_name)

        self.write_model.add_global_scope(scope_name, _blocking_scope)
        try:
            yield self
        finally:
            scopes: dict[str, Any] = self.write_model.__dict__.get("__arvel_global_scopes__", {})
            scopes.pop(scope_name, None)


__all__ = [
    "ImmutableReadModelError",
    "ReadModelPolicy",
    "ReadModelPolicyViolationError",
]
