"""Request and response bodies of the identity routes (snake_case, section 11.1)."""

import re
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class PasskeyRegisterVerify(BaseModel):
    credential: dict[str, Any]  # navigator.credentials.create() answer, JSON-encoded
    name: str = Field(default="Clé d'accès", min_length=1, max_length=64)


class PasskeyLoginVerify(BaseModel):
    credential: dict[str, Any]  # navigator.credentials.get() answer, JSON-encoded


class PasskeyOut(BaseModel):
    id: UUID
    name: str | None
    created_at: datetime
    last_used_at: datetime | None


class PasskeyList(BaseModel):
    data: list[PasskeyOut]


class PasskeyRename(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class StepUpRequest(BaseModel):
    method: Literal["passkey", "magic_link"]
    credential: dict[str, Any] | None = None  # required for "passkey"

    @model_validator(mode="after")
    def _passkey_needs_credential(self) -> "StepUpRequest":
        if self.method == "passkey" and self.credential is None:
            raise ValueError("credential is required for the passkey method")
        return self


class StepUpVerify(BaseModel):
    token: str = Field(min_length=1, max_length=128)


USERNAME_PATTERN = r"^[a-z0-9_.]{3,30}$"
MIN_BIRTH_YEAR = 1900


class Counters(BaseModel):
    unread_messages: int
    notifications: int


class MeOut(BaseModel):
    """The signed-in person's own account. Never shown to anybody else."""

    id: UUID
    email: str
    username: str
    display_name: str
    bio: str | None
    locale: str
    country_code: str
    profile_completed: bool
    roles: list[str]
    flags: dict[str, bool]
    is_minor: bool | None  # None until the birth year is known
    erasure_requested_at: datetime | None
    counters: Counters
    version: int  # If-Match value of PATCH /v1/me


class CompleteProfile(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    display_name: str = Field(min_length=1, max_length=60)
    birth_year: int = Field(ge=MIN_BIRTH_YEAR)  # upper bound checked against the clock
    accept_terms: Literal[True]
    terms_version: str = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def _normalise(self) -> "CompleteProfile":
        self.username = self.username.strip().lower()
        self.display_name = self.display_name.strip()
        if not re.fullmatch(USERNAME_PATTERN, self.username) or not self.display_name:
            raise ValueError("invalid username or display name")
        return self


class UsernameSuggestion(BaseModel):
    username: str


class ProfilePatch(BaseModel):
    """Only the fields sent are changed; `bio` set to blank clears it."""

    model_config = ConfigDict(extra="forbid")

    username: str | None = Field(default=None, min_length=3, max_length=30)
    display_name: str | None = Field(default=None, min_length=1, max_length=60)
    bio: str | None = Field(default=None, max_length=500)
    locale: Literal["fr-FR"] | None = None  # French only for now (web i18n/routing.ts)

    @model_validator(mode="after")
    def _normalise(self) -> "ProfilePatch":
        for required in ("username", "display_name", "locale"):
            if required in self.model_fields_set and getattr(self, required) is None:
                raise ValueError(f"{required} cannot be null")
        if self.username is not None:
            self.username = self.username.strip().lower()
            if not re.fullmatch(USERNAME_PATTERN, self.username):
                raise ValueError("invalid username")
        if self.display_name is not None:
            self.display_name = self.display_name.strip()
            if not self.display_name:
                raise ValueError("display name cannot be blank")
        return self

    def changes(self) -> dict[str, str | None]:
        sent = self.model_dump(exclude_unset=True)
        if "bio" in sent:
            sent["bio"] = (sent["bio"] or "").strip() or None
        return sent


class PublicProfile(BaseModel):
    """What anybody can see. Never the e-mail, location, age or account status."""

    username: str
    display_name: str
    bio: str | None
    member_since: date
    followers_count: int
    following_count: int
