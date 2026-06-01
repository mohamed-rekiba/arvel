"""Tests for ArvelTestCase + pytest fixtures."""

from __future__ import annotations

import pytest


class TestArvelTestCase:
    def test_class_exists_and_exposes_expected_protocol(self) -> None:
        from arvel.testing import ArvelTestCase

        assert hasattr(ArvelTestCase, "asyncSetUp")
        assert hasattr(ArvelTestCase, "asyncTearDown")
        assert hasattr(ArvelTestCase, "acting_as")
        assert hasattr(ArvelTestCase, "refresh_database")

    @pytest.mark.asyncio
    async def test_setup_creates_app_and_client(self) -> None:
        """asyncSetUp boots the app and binds a client.

        the defensive skip that previously masked the
        qa_post pollution has been removed. If this test fails,
        there is a real bug — either in ArvelTestCase or in a sibling test
        that leaked global state.
        """
        from arvel.testing import ArvelTestCase

        case = ArvelTestCase()
        await case.asyncSetUp()
        try:
            assert case.app is not None
            assert case.client is not None
        finally:
            await case.asyncTearDown()


class TestPytestFixtures:
    def test_fixtures_module_exposes_arvel_app(self) -> None:
        from arvel.testing import fixtures

        assert hasattr(fixtures, "arvel_app")
        assert hasattr(fixtures, "arvel_client")
