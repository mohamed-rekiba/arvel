"""Runtime read-model policy guard.

Verifies that :class:`arvel.database.ReadModelPolicy` raises
:class:`ReadModelPolicyViolation` when storefront paths attempt to query
``Product`` (the write-side model) directly while a policy guard is active.

These tests complement the static source-inspection tests in
``test_049_storefront_category_and_cart_guard.py`` by confirming the guard
works at the ORM layer, not just as a textual assertion.
"""

from __future__ import annotations

import pytest
from arvel.database.policy import ReadModelPolicy, ReadModelPolicyViolationError


class _FakeProductCatalog:
    """Minimal stub for the read-model side of the policy."""

    __name__ = "ProductCatalog"


class _FakeWriteModel:
    """Minimal stub for the write-model side of the policy.


    Mirrors the ``add_global_scope`` / ``__arvel_global_scopes__`` API that
    :class:`arvel.database.Model` exposes so the policy can be tested without
    a live database connection.
    """

    __name__ = "Product"
    __arvel_global_scopes__: dict[str, object] = {}

    @classmethod
    def add_global_scope(cls, name: str, scope: object) -> None:
        if "__arvel_global_scopes__" not in cls.__dict__:
            cls.__arvel_global_scopes__ = {}
        cls.__arvel_global_scopes__[name] = scope

    @classmethod
    def _trigger_scopes(cls) -> None:
        """Simulate what QueryBuilder._apply_global_scopes() does."""
        for fn in list(cls.__dict__.get("__arvel_global_scopes__", {}).values()):
            fn(None)  # ReadModelPolicy scope ignores the QB arg


def test_policy_guard_blocks_write_model_query() -> None:
    write = _FakeWriteModel
    write.__arvel_global_scopes__ = {}

    policy = ReadModelPolicy(read_model=_FakeProductCatalog, write_model=write)

    with policy.guard(), pytest.raises(ReadModelPolicyViolationError) as exc_info:
        write._trigger_scopes()

    assert "Product" in str(exc_info.value)
    assert "ProductCatalog" in str(exc_info.value)


def test_policy_guard_removes_scope_on_exit() -> None:
    write = _FakeWriteModel
    write.__arvel_global_scopes__ = {}

    policy = ReadModelPolicy(read_model=_FakeProductCatalog, write_model=write)

    with policy.guard():
        pass  # enter and exit

    # Scope must be cleaned up — no violation after guard exits.
    write._trigger_scopes()  # should not raise


def test_policy_guard_scope_name_is_unique_per_instance() -> None:
    write = _FakeWriteModel
    write.__arvel_global_scopes__ = {}

    p1 = ReadModelPolicy(read_model=_FakeProductCatalog, write_model=write)
    p2 = ReadModelPolicy(read_model=_FakeProductCatalog, write_model=write)

    assert p1._SCOPE_PREFIX + str(id(p1)) != p1._SCOPE_PREFIX + str(id(p2))


def test_policy_violation_message_names_both_models() -> None:
    err = ReadModelPolicyViolationError("Product", "ProductCatalog")
    assert "Product" in str(err)
    assert "ProductCatalog" in str(err)


def test_nested_guards_are_independent() -> None:
    write = _FakeWriteModel
    write.__arvel_global_scopes__ = {}

    p1 = ReadModelPolicy(read_model=_FakeProductCatalog, write_model=write)
    p2 = ReadModelPolicy(read_model=_FakeProductCatalog, write_model=write)

    with p1.guard():
        with p2.guard():
            assert len(write.__arvel_global_scopes__) == 2

        # p2 removed; p1 scope still present
        assert len(write.__arvel_global_scopes__) == 1
        with pytest.raises(ReadModelPolicyViolationError):
            write._trigger_scopes()

    assert len(write.__arvel_global_scopes__) == 0
