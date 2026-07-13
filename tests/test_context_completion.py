"""Conditional adds, bulk ops, the full hidden-channel mirror, and hidden-aware scope."""

from __future__ import annotations

from arvel.support.context import Context

# --- conditional adds -----------------------------------------------------------


def test_add_if_only_adds_when_absent() -> None:
    Context.add("k", "original")
    Context.add_if("k", "ignored")
    Context.add_if("fresh", "v")
    assert Context.get("k") == "original"
    assert Context.get("fresh") == "v"


def test_add_hidden_if_only_adds_when_absent() -> None:
    Context.add_hidden("k", "original")
    Context.add_hidden_if("k", "ignored")
    Context.add_hidden_if("fresh", "v")
    assert Context.get_hidden("k") == "original"
    assert Context.get_hidden("fresh") == "v"


# --- bulk ops ---------------------------------------------------------------------


def test_add_accepts_a_mapping() -> None:
    Context.add({"a": 1, "b": 2})
    assert Context.get("a") == 1
    assert Context.get("b") == 2


def test_add_hidden_accepts_a_mapping() -> None:
    Context.add_hidden({"a": 1, "b": 2})
    assert Context.get_hidden("a") == 1
    assert Context.get_hidden("b") == 2


def test_forget_accepts_a_list_and_ignores_unknown_keys() -> None:
    Context.add({"a": 1, "b": 2, "c": 3})
    Context.forget(["a", "c", "never-there"])
    assert Context.all() == {"b": 2}


def test_forget_hidden_accepts_a_list() -> None:
    Context.add_hidden({"a": 1, "b": 2})
    Context.forget_hidden(["a"])
    assert Context.all_hidden() == {"b": 2}


# --- hidden mirror ------------------------------------------------------------------


def test_hidden_ops_mirror_visible_ops() -> None:
    Context.add_hidden("scalar", 1)
    Context.push_hidden("stack", "x", "y")
    assert Context.hidden_stack_contains("stack", "x") is True
    assert Context.pop_hidden("stack") == "y"
    assert Context.pull_hidden("scalar") == 1
    assert Context.missing_hidden("scalar") is True
    Context.add_hidden({"a": 1, "b": 2, "c": 3})
    assert Context.only_hidden(["a", "b"]) == {"a": 1, "b": 2}
    assert Context.except_hidden(["a", "b", "stack"]) == {"c": 3}
    Context.forget_hidden("c")
    assert Context.has_hidden("c") is False


def test_hidden_never_leaks_into_visible_surface() -> None:
    Context.push_hidden("stack", "x")
    Context.add_hidden("k", "v")
    assert Context.all() == {}
    assert Context.stack_contains("stack", "x") is False


# --- scope with hidden ----------------------------------------------------------------


def test_scope_applies_and_restores_both_channels() -> None:
    Context.add("keep", "v")
    Context.add_hidden("hkeep", "hv")
    with Context.scope(data={"tmp": 1}, hidden={"htmp": 2}):
        assert Context.get("tmp") == 1
        assert Context.get_hidden("htmp") == 2
        Context.add("inner", True)
        Context.add_hidden("hinner", True)
    assert Context.all() == {"keep": "v"}
    assert Context.all_hidden() == {"hkeep": "hv"}


def test_scope_kwargs_still_add_visible_values() -> None:
    with Context.scope(request_id="r-1"):
        assert Context.get("request_id") == "r-1"
    assert Context.missing("request_id") is True


def test_scope_restores_on_exception() -> None:
    Context.add_hidden("h", 1)
    try:
        with Context.scope(hidden={"h": 2}):
            assert Context.get_hidden("h") == 2
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert Context.get_hidden("h") == 1
