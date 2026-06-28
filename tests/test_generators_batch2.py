"""make:* generators — second batch (Laravel artisan parity). Each scaffolds a typed, parseable stub
that imports a real arvel base class, into the conventional folder. Exercises the unit-testable
``generate()`` core (it takes a base path)."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from arvel.console.generators import generate


def _exec_module(path: Path, modname: str) -> ModuleType:
    """Actually import the generated file (runs its `from arvel... import Base` line) so a stub that
    references a non-existent base class fails loudly — the green-but-broken guard."""
    spec = importlib.util.spec_from_file_location(modname, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# kind -> (expected relative path, a substring the stub must contain)
_CASES = {
    "job": ("app/jobs/process_payment.py", "class ProcessPayment(Job)"),
    "policy": ("app/policies/post_policy.py", "class PostPolicy"),
    "notification": ("app/notifications/invoice_paid.py", "class InvoicePaid(Notification)"),
    "mail": ("app/mail/order_shipped.py", "class OrderShipped(Mailable)"),
    "rule": ("app/rules/uppercase.py", "class Uppercase(Rule)"),
    "seeder": ("database/seeders/post_seeder.py", "class PostSeeder(Seeder)"),
    "factory": ("database/factories/post_factory.py", "class PostFactory(Factory)"),
    "provider": ("app/providers/route_provider.py", "class RouteProvider(ServiceProvider)"),
}

_CLASS_NAMES = {
    "job": "ProcessPayment",
    "policy": "PostPolicy",
    "notification": "InvoicePaid",
    "mail": "OrderShipped",
    "rule": "Uppercase",
    "seeder": "PostSeeder",
    "factory": "PostFactory",
    "provider": "RouteProvider",
}


@pytest.mark.parametrize("kind", list(_CASES))
def test_generator_writes_a_parseable_stub(kind: str, tmp_path: Path) -> None:
    rel, contains = _CASES[kind]
    target = generate(kind, _CLASS_NAMES[kind], base=tmp_path)
    assert target == tmp_path / rel
    source = target.read_text()
    ast.parse(source)  # valid Python
    assert contains in source
    # strongest guard: importing it executes the base-class import against real arvel
    module = _exec_module(target, f"gen_{kind}")
    assert hasattr(module, _CLASS_NAMES[kind])


def test_generator_refuses_to_overwrite(tmp_path: Path) -> None:
    generate("job", "ProcessPayment", base=tmp_path)
    with pytest.raises(FileExistsError):
        generate("job", "ProcessPayment", base=tmp_path)
