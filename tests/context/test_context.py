"""Tests for the Context store — FR-001 and FR-002."""

from __future__ import annotations

from arvel.context.context_store import Context

# ---------------------------------------------------------------------------
# FR-001: Context Store — basic operations
# ---------------------------------------------------------------------------


class TestContextAddAndGet:
    """FR-001.1 / FR-001.2: add and get values."""

    async def test_add_and_get_returns_value(self) -> None:
        Context.flush()
        Context.add("tenant_id", 42)
        assert Context.get("tenant_id") == 42

    async def test_get_missing_key_returns_default(self) -> None:
        Context.flush()
        assert Context.get("nonexistent") is None

    async def test_get_missing_key_returns_custom_default(self) -> None:
        Context.flush()
        assert Context.get("missing", "fallback") == "fallback"

    async def test_add_overwrites_existing_key(self) -> None:
        Context.flush()
        Context.add("key", "old")
        Context.add("key", "new")
        assert Context.get("key") == "new"

    async def test_add_multiple_keys(self) -> None:
        Context.flush()
        Context.add("a", 1)
        Context.add("b", 2)
        assert Context.get("a") == 1
        assert Context.get("b") == 2


class TestContextHas:
    """FR-001.3: has() checks existence."""

    async def test_has_returns_true_for_existing_key(self) -> None:
        Context.flush()
        Context.add("exists", True)
        assert Context.has("exists") is True

    async def test_has_returns_false_for_missing_key(self) -> None:
        Context.flush()
        assert Context.has("missing") is False

    async def test_has_returns_true_for_hidden_key(self) -> None:
        Context.flush()
        Context.add_hidden("secret", "value")
        assert Context.has("secret") is True


class TestContextForget:
    """FR-001.4: forget() removes a key."""

    async def test_forget_removes_key(self) -> None:
        Context.flush()
        Context.add("tenant_id", 42)
        Context.forget("tenant_id")
        assert Context.get("tenant_id") is None

    async def test_forget_nonexistent_key_does_not_raise(self) -> None:
        Context.flush()
        Context.forget("nonexistent")


class TestContextAll:
    """FR-001.5: all() returns a shallow copy."""

    async def test_all_returns_all_visible_pairs(self) -> None:
        Context.flush()
        Context.add("a", 1)
        Context.add("b", 2)
        result = Context.all()
        assert result == {"a": 1, "b": 2}

    async def test_all_excludes_hidden(self) -> None:
        Context.flush()
        Context.add("visible", True)
        Context.add_hidden("hidden", True)
        result = Context.all()
        assert "hidden" not in result
        assert "visible" in result

    async def test_all_returns_copy_not_reference(self) -> None:
        Context.flush()
        Context.add("key", "value")
        copy = Context.all()
        copy["key"] = "mutated"
        assert Context.get("key") == "value"


class TestContextHidden:
    """FR-001.6 / FR-001.7 / FR-001.8: hidden context."""

    async def test_add_hidden_and_get_hidden(self) -> None:
        Context.flush()
        Context.add_hidden("api_key", "secret123")
        assert Context.get_hidden("api_key") == "secret123"

    async def test_get_hidden_missing_returns_default(self) -> None:
        Context.flush()
        assert Context.get_hidden("missing") is None
        assert Context.get_hidden("missing", "fallback") == "fallback"

    async def test_all_hidden_returns_copy(self) -> None:
        Context.flush()
        Context.add_hidden("k1", "v1")
        Context.add_hidden("k2", "v2")
        result = Context.all_hidden()
        assert result == {"k1": "v1", "k2": "v2"}

    async def test_hidden_not_in_visible(self) -> None:
        Context.flush()
        Context.add_hidden("secret", "x")
        assert "secret" not in Context.all()


class TestContextPush:
    """FR-001.9: push() appends to a stack."""

    async def test_push_creates_list(self) -> None:
        Context.flush()
        Context.push("breadcrumbs", "step_1")
        assert Context.get("breadcrumbs") == ["step_1"]

    async def test_push_appends_to_existing_list(self) -> None:
        Context.flush()
        Context.push("breadcrumbs", "step_1")
        Context.push("breadcrumbs", "step_2")
        assert Context.get("breadcrumbs") == ["step_1", "step_2"]

    async def test_push_multiple_values(self) -> None:
        Context.flush()
        Context.push("tags", "a", "b", "c")
        assert Context.get("tags") == ["a", "b", "c"]

    async def test_push_to_non_list_key_converts(self) -> None:
        Context.flush()
        Context.add("key", "scalar")
        Context.push("key", "appended")
        assert Context.get("key") == ["scalar", "appended"]


class TestContextFlush:
    """FR-001.10: flush() clears everything."""

    async def test_flush_clears_visible_and_hidden(self) -> None:
        Context.flush()
        Context.add("a", 1)
        Context.add_hidden("b", 2)
        Context.flush()
        assert Context.all() == {}
        assert Context.all_hidden() == {}


# ---------------------------------------------------------------------------
# FR-002: Dehydration / Hydration
# ---------------------------------------------------------------------------


class TestDehydrate:
    """FR-002.1 / FR-002.7: dehydrate() serialization."""

    async def test_dehydrate_returns_visible_data(self) -> None:
        Context.flush()
        Context.add("tenant_id", 42)
        Context.add("locale", "en")
        data = Context.dehydrate()
        assert data == {"tenant_id": 42, "locale": "en"}

    async def test_dehydrate_excludes_hidden(self) -> None:
        Context.flush()
        Context.add("visible", "yes")
        Context.add_hidden("secret", "no")
        data = Context.dehydrate()
        assert "secret" not in data
        assert "visible" in data


class TestHydrate:
    """FR-002.2: hydrate() restoration."""

    async def test_hydrate_restores_data(self) -> None:
        Context.flush()
        Context.hydrate({"tenant_id": 42, "locale": "fr"})
        assert Context.get("tenant_id") == 42
        assert Context.get("locale") == "fr"

    async def test_hydrate_merges_with_existing(self) -> None:
        Context.flush()
        Context.add("existing", "keep")
        Context.hydrate({"new_key": "added"})
        assert Context.get("existing") == "keep"
        assert Context.get("new_key") == "added"


class TestDehydrationHooks:
    """FR-002.3 / FR-002.4 / FR-002.5 / FR-002.6: hooks."""

    async def test_dehydrating_callback_modifies_data(self) -> None:
        Context.flush()
        Context._clear_hooks()
        Context.add("request_id", "abc")

        def add_locale(data: dict[str, object]) -> dict[str, object]:
            return {**data, "locale": "fr"}

        Context.dehydrating(add_locale)
        result = Context.dehydrate()
        assert result["locale"] == "fr"
        Context._clear_hooks()

    async def test_hydrated_callback_runs_after_restore(self) -> None:
        Context.flush()
        Context._clear_hooks()
        side_effects: list[str] = []

        def on_hydrated(data: dict[str, object]) -> None:
            side_effects.append(f"locale={data.get('locale')}")

        Context.hydrated(on_hydrated)
        Context.hydrate({"locale": "de"})
        assert side_effects == ["locale=de"]
        Context._clear_hooks()

    async def test_multiple_dehydrating_callbacks_run_in_order(self) -> None:
        Context.flush()
        Context._clear_hooks()
        order: list[int] = []

        def hook1(data: dict[str, object]) -> dict[str, object]:
            order.append(1)
            return {**data, "h1": True}

        def hook2(data: dict[str, object]) -> dict[str, object]:
            order.append(2)
            return {**data, "h2": True}

        Context.dehydrating(hook1)
        Context.dehydrating(hook2)
        result = Context.dehydrate()
        assert order == [1, 2]
        assert result["h1"] is True
        assert result["h2"] is True
        Context._clear_hooks()

    async def test_multiple_hydrated_callbacks_run_in_order(self) -> None:
        Context.flush()
        Context._clear_hooks()
        order: list[int] = []

        def hook1(data: dict[str, object]) -> None:
            order.append(1)

        def hook2(data: dict[str, object]) -> None:
            order.append(2)

        Context.hydrated(hook1)
        Context.hydrated(hook2)
        Context.hydrate({"key": "val"})
        assert order == [1, 2]
        Context._clear_hooks()
