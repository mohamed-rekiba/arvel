"""Give every newly registered user the baseline `customer` role."""

from __future__ import annotations

from arvel.auth.events import Registered
from arvel.events.listener import Listener
from arvel.logging.facade import Log

from app.models.user import User


class AssignCustomerRole(Listener[Registered]):
    """Self-serve signups land outside RBAC otherwise — seeded users get it from the seeder."""

    def __init__(self) -> None:
        # Explicit ctor so the container auto-wires it; it refuses to build a
        # class whose __init__ is object.__init__ unless explicitly bound.
        super().__init__()

    async def handle(self, event: Registered) -> None:
        if event.user_id is None:
            return
        user = await User.where(User.id == int(event.user_id)).first()
        if user is None:
            return
        await user.assign_role("customer")
        Log.debug("registration.customer_role_assigned", user_id=event.user_id)
