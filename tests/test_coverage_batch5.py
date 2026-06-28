"""Coverage — routing verbs/url/bind/signed-url, Job.handle, queue manager (app path)."""

from __future__ import annotations

import pytest

from arvel.routing import Router

SIGN_KEY = "x" * 40


def _noop(request: object, **kwargs: object) -> dict[str, object]:
    return {}


def test_router_verbs_register() -> None:
    router = Router()
    router.get("/g", _noop)
    router.put("/p", _noop, name="p")
    router.patch("/pa", _noop)
    router.delete("/d", _noop)
    assert len(router.routes()) == 4


def test_url_reverse_and_unknown() -> None:
    router = Router()
    router.get("/users/{id}", _noop, name="user.show")
    assert router.url("user.show", id=7) == "/users/7"
    with pytest.raises(KeyError, match="No route named"):
        router.url("does.not.exist")


def test_bind_and_model_binding() -> None:
    router = Router()
    router.bind("token", lambda v: v.upper())
    assert "token" in router._bindings

    class Thing:
        @staticmethod
        async def find(v: object) -> object:
            return v

    router.model("thing", Thing)
    assert "thing" in router._bindings


def test_signed_url_roundtrip_and_tamper() -> None:
    router = Router()
    router.get("/download/{id}", _noop, name="download")
    url = router.signed_url("download", key=SIGN_KEY, id=5)
    assert router.has_valid_signature(url, key=SIGN_KEY)
    assert not router.has_valid_signature(url + "tampered", key=SIGN_KEY)
    assert not router.has_valid_signature("/no-signature-here", key=SIGN_KEY)


async def test_job_handle_must_be_implemented() -> None:
    from arvel.queue import Job

    with pytest.raises(NotImplementedError):
        await Job().handle()


def test_queue_manager_resolves_from_app() -> None:
    import arvel.queue as queue_mod
    from arvel.kernel import Application, set_application
    from arvel.queue import QueueManager

    app = Application()
    bound = QueueManager()
    app.instance("queue", bound)
    set_application(app)
    try:
        assert queue_mod._queue_manager() is bound
    finally:
        set_application(None)
