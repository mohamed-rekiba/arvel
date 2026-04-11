"""Tests for the shared CLI UX utilities."""

from __future__ import annotations

from arvel.cli.ui import BANNER, CliConsole, InquirerPreloader


class TestCliConsole:
    """Verify CliConsole lazy initialization and output methods."""

    def test_console_is_lazy(self) -> None:
        ui = CliConsole()
        assert ui._console is None

    def test_console_property_creates_instance(self) -> None:
        ui = CliConsole()
        c = ui.console
        assert c is not None
        assert ui._console is c

    def test_console_property_returns_same_instance(self) -> None:
        ui = CliConsole()
        c1 = ui.console
        c2 = ui.console
        assert c1 is c2

    def test_banner_constant_is_string(self) -> None:
        assert isinstance(BANNER, str)
        assert len(BANNER) > 20


class TestCliValidationError:
    """Verify CliValidationError carries the message."""

    def test_message_attribute(self) -> None:
        from arvel.cli.exceptions import CliValidationError

        exc = CliValidationError("bad input")
        assert exc.message == "bad input"
        assert str(exc) == "bad input"


class TestInquirerPreloader:
    """Verify the InquirerPy background preloader."""

    def test_preloader_stop_is_safe(self) -> None:
        preloader = InquirerPreloader()
        preloader.stop()

    def test_preloader_get_returns_module(self) -> None:
        preloader = InquirerPreloader()
        mod = preloader.get()
        assert mod is not None
        preloader.stop()


class TestCliPluginProtocol:
    """Verify the CliPlugin protocol is runtime-checkable."""

    def test_protocol_runtime_check(self) -> None:
        from arvel.cli.plugins._base import CliPlugin

        class _FakePlugin:
            name = "test"
            help = "A test plugin."

            def register(self, app: object) -> None:
                pass

        assert isinstance(_FakePlugin(), CliPlugin)

    def test_non_conforming_type_fails_check(self) -> None:
        from arvel.cli.plugins._base import CliPlugin

        class _Bad:
            pass

        assert not isinstance(_Bad(), CliPlugin)
