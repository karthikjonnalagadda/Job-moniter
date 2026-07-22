"""User model — authentication-ready, authentication NOT implemented.

The MVP is single-user: everything defaults to ``DEFAULT_USER_ID`` and the app
is fully functional with no login. This model exists so multi-user support is a
data + middleware change later, not a schema redesign:

* ``user_id`` is the stable business key used to scope repositories/services.
* ``auth_provider`` / ``external_subject`` are placeholders for a future JWT/OAuth
  identity, unused today. Adding auth means: a login route, middleware that
  resolves the request's ``user_id``, and passing it where ``DEFAULT_USER_ID`` is
  currently defaulted — no model or repository signature changes.
"""

from __future__ import annotations

from pydantic import Field

from app.models.base import MongoDocument
from app.models.common import DEFAULT_USER_ID
from app.models.enums import UserRole


class User(MongoDocument):
    """A platform user. In single-user mode exactly one exists (``default``)."""

    user_id: str = DEFAULT_USER_ID
    email: str
    display_name: str | None = None
    roles: list[UserRole] = Field(default_factory=lambda: [UserRole.OWNER])
    is_active: bool = True

    # ---- Reserved for future authentication (not used in the MVP) ----
    auth_provider: str | None = None  # e.g. "local" | "google" | "github"
    external_subject: str | None = None  # OAuth/JWT subject claim
