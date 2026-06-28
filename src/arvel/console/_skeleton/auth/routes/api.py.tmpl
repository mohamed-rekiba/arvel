"""API routes — the "api" group (served under /api), with a bearer-token auth flow.

Handlers are typed with ``arvel.Schema`` so the OpenAPI request/response schemas generate (browse them
at /schema) AND the request body is validated — a missing or malformed body is a clean 400, not a 500:
  POST /api/login  -> verify credentials, issue a personal access token
  GET  /api/user   -> protected; requires ``Authorization: Bearer <token>``
"""

from arvel import Route, Schema, abort
from arvel.auth.tokens import TokenGuard, create_token
from arvel.http import Response
from arvel.security import Hasher

from app.models.user import User


class HealthStatus(Schema):
    status: str


class Credentials(Schema):
    email: str
    password: str


class UserOut(Schema):
    id: int
    name: str
    email: str


async def health(request) -> HealthStatus:
    return HealthStatus(status="ok")


async def login(request, data: Credentials):  # `data: Credentials` → parsed + validated request body
    user = await User.query().where("email", data.email).first()
    if user is None or not Hasher().check(data.password, user.password):
        abort(401, "Invalid credentials")
    token, _ = await create_token(user, name="api")
    return Response(content={"token": token}, status=200)


async def me(request) -> UserOut:
    user_id = await TokenGuard().user_id(request)
    if user_id is None:
        abort(401, "Unauthenticated")
    user = await User.find(user_id)
    return UserOut(id=user.id, name=user.name, email=user.email)


Route.get("/health", health, name="api.health")
Route.post("/login", login, name="api.login")
Route.get("/user", me, name="api.user").secure("bearer")  # shows the lock + 'Authorize' in API docs
