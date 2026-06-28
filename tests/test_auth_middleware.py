"""Auth (doc 15) — AuthenticateMiddleware binds current_user per request. Test-first."""

from __future__ import annotations

from typing import Any

from arvel import Application
from arvel.auth import current_user
from arvel.http import HttpKernel
from arvel.http.middleware import AuthenticateMiddleware
from arvel.kernel import set_application
from arvel.testing import client


class FakeUser:
    def __init__(self, identifier: int) -> None:
        self.id = identifier


def test_authenticate_middleware_binds_and_clears_user() -> None:
    app = Application()

    def resolver(request: Any) -> FakeUser | None:
        return FakeUser(7) if request.header("authorization") else None

    app.instance("user_resolver", resolver)
    set_application(app)
    try:

        def handler(request: Any) -> dict[str, Any]:
            user = current_user.get()
            return {"user_id": user.id if user is not None else None}

        kernel = HttpKernel()
        kernel.global_middleware = [AuthenticateMiddleware]
        kernel.get("/", handler)
        with client(kernel.build()) as http:
            assert http.get("/", headers={"authorization": "Bearer x"}).json() == {"user_id": 7}
            assert http.get("/").json() == {"user_id": None}  # no token → guest
        # bound user does not leak past the request
        assert current_user.get() is None
    finally:
        set_application(None)
