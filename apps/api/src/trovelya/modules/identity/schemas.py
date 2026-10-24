"""Request and response bodies of the identity routes (snake_case, section 11.1)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SessionOut(BaseModel):
    """A sign-in session as shown in the account settings. Never the IP or the user agent."""

    id: UUID
    current: bool
    created_at: datetime
    last_used_at: datetime
    device_label: str | None
    country_code: str | None


class SessionList(BaseModel):
    data: list[SessionOut]
