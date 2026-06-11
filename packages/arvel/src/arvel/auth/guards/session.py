"""SessionGuard — reads from request.state.session (Arvel SessionData)."""

from __future__ import annotations

from typing import Any, cast

from arvel.auth.guard import Guard, UserResolver
from arvel.auth.mixins import Authenticatable
from arvel.facades.hash import Hash


class SessionGuard(Guard):
    """Authenticates via Arvel's SessionData stored at request.state.session."""

    def __init__(
        self,
        *,
        resolver: UserResolver,
        session_key: str = "_auth_id",
        password_field: str = "password",  # noqa: S107 -- default field name, not a credential
    ) -> None:
        self._resolver = resolver
        self._session_key = session_key
        self._password_field = password_field

    async def user(self, request: Any) -> Any | None:
        session = self._get_session(request)
        if session is None:
            return None
        user_id = session.get(self._session_key)
        if not isinstance(user_id, str):
            return None
        user = await self._resolver.by_id(user_id)
        if isinstance(user, Authenticatable) and user.is_suspended:
            return None
        return user

    async def attempt(self, credentials: dict[str, object], request: Any) -> bool:
        # Can't authenticate via session if there's no session to write to —
        # don't report success the caller can't act on.
        if self._get_session(request) is None:
            return False

        user = await self._resolver.by_credentials(credentials)
        if user is None:
            return False

        plain = credentials.get("password")
        if not isinstance(plain, str):
            return False

        stored_hash = self._get_password(user)
        if stored_hash is None:
            return False

        if not Hash.check(plain, stored_hash):
            return False

        await self.login(user, request)
        return True

    def _get_password(self, user: Any) -> str | None:
        """Extract the hashed password from a user object or dict."""
        field: Any
        val: Any
        if isinstance(user, dict):
            user_dict = cast("dict[str, Any]", user)
            # Support custom field names via _auth_password_field
            field = user_dict.get("_auth_password_field", self._password_field)
            val = user_dict.get(str(field))
        else:
            field = getattr(user, "_auth_password_field", self._password_field)
            val = getattr(user, str(field), None)
        return str(val) if val is not None else None

    async def login(self, user: Any, request: Any) -> None:
        session = self._get_session(request)
        if session is None:
            return
        # Prevent session fixation — regenerate ID before writing the user key.
        session.regenerate()
        # Rotate the CSRF token so a pre-login token can't be replayed post-login.
        if hasattr(session, "regenerate_token"):
            session.regenerate_token()
        user_id = str(getattr(user, "id", ""))
        session.put(self._session_key, user_id)

    async def logout(self, request: Any) -> None:
        session = self._get_session(request)
        if session is None:
            return
        # Flush + rotate the id so nothing (auth key, flash, CSRF token) survives
        # logout under the old session id. Falls back to forget for dict-like
        # sessions that don't implement invalidate().
        if hasattr(session, "invalidate"):
            session.invalidate()
        else:
            session.forget(self._session_key)

    @staticmethod
    def _get_session(request: Any) -> Any | None:
        state = getattr(request, "state", None)
        if state is None:
            return None
        return getattr(state, "session", None)
