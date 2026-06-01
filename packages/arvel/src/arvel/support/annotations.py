"""Annotation resolution helpers.

Shared between routing, form-request handling, and the ORM's attribute /
relation introspection. The same primitive — given a callable or class,
resolve its type hints honouring PEP 563 (``from __future__ import
annotations``) and closure-scope captures — appears in three places by
; we own it once, here.
"""

from __future__ import annotations

import inspect
import typing
from collections.abc import Callable
from typing import Any

__all__ = ["resolve_annotations"]


def resolve_annotations(
    target: Callable[..., Any] | type,
    *,
    caller_locals: dict[str, Any] | None = None,
    extra_namespace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve string (PEP 563) annotations to runtime types.

    ``target`` may be a callable (function, method, lambda) or a class. The
    result is a mapping of parameter (or attribute) name → resolved type.

    Resolution order:

    1. ``typing.get_type_hints(target, localns=...)`` with the supplied
       ``extra_namespace`` and ``caller_locals`` merged. If this succeeds, its
       output is returned verbatim — fastest path.
    2. If that fails (e.g. a forward-ref that's only visible in the caller's
       closure), per-parameter ``eval`` against the same namespaces. Each
       failure leaves the annotation as a string so the caller can decide.

    ``caller_locals`` is intended for test-time use: when a developer declares
    a ``FormRequest`` subclass inside a test function, the closure's locals
    are the only place its name is bound at decoration time. The container's
    documentation (``docs/concepts/container.md``) labels this as test-only;
    production handlers should keep their types at module scope.
    """
    namespace: dict[str, Any] = {}
    if extra_namespace:
        namespace.update(extra_namespace)
    if caller_locals:
        namespace.update(caller_locals)

    try:
        return typing.get_type_hints(target, localns=namespace)
    # Per-element fallback below; this path must never crash callers.
    except Exception:  # nosec B110
        pass

    if inspect.isclass(target):
        return _resolve_class_annotations(target, namespace)
    return _resolve_callable_annotations(target, namespace)


def _resolve_class_annotations(cls: type, namespace: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    glb = getattr(cls, "__module__", None)
    module_globals: dict[str, Any] = {}
    if glb:
        mod = inspect.getmodule(cls)
        if mod is not None:
            module_globals = dict(getattr(mod, "__dict__", {}))
    raw = getattr(cls, "__annotations__", {})
    for name, ann in raw.items():
        if isinstance(ann, str):
            try:
                # Bounded by design: `ann` is a developer-authored type
                # annotation literal, never user input. Namespaces are the
                # defining module's globals plus a small caller-supplied
                # namespace. Mirrors typing.get_type_hints internals.
                # `ann` is a developer-authored type annotation, never user input.
                out[name] = eval(ann, module_globals, namespace)  # noqa: S307  # nosec B307
            except Exception:
                # Leave annotation as string on failure (matches typing.get_type_hints).
                out[name] = ann
        else:
            out[name] = ann
    return out


def _resolve_callable_annotations(
    fn: Callable[..., Any], namespace: dict[str, Any]
) -> dict[str, Any]:
    sig = inspect.signature(fn)
    out: dict[str, Any] = {}
    glb = getattr(fn, "__globals__", {})
    for name, param in sig.parameters.items():
        ann = param.annotation
        if ann is inspect.Parameter.empty:
            continue
        if isinstance(ann, str):
            try:
                # Same rationale as in _resolve_class_annotations.
                # `ann` is a developer-authored type annotation, never user input.
                out[name] = eval(ann, glb, namespace)  # noqa: S307  # nosec B307
            except Exception:
                # Leave annotation as string on failure.
                out[name] = ann
        else:
            out[name] = ann
    return_ann = sig.return_annotation
    if return_ann is not inspect.Signature.empty:
        if isinstance(return_ann, str):
            try:
                # `return_ann` is a developer-authored type annotation, never user input.
                out["return"] = eval(return_ann, glb, namespace)  # noqa: S307  # nosec B307
            except Exception:
                # Leave as string on failure.
                out["return"] = return_ann
        else:
            out["return"] = return_ann
    return out
