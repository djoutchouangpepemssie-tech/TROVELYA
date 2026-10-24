"""Request and response bodies of the identity routes (snake_case, section 11.1)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


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


class MagicLinkRequest(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)
    captcha_token: str | None = Field(default=None, max_length=4096)


class MagicLinkVerify(BaseModel):
    token: str = Field(min_length=1, max_length=128)


class SignInResult(BaseModel):
    user_id: UUID
    is_new: bool
    profile_completed: bool
