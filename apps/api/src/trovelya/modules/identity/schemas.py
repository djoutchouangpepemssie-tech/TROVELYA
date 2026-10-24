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


class EmailChangeRequest(BaseModel):
    new_email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)


class EmailChangeVerify(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class PlaceOut(BaseModel):
    label: str
    place_name: str  # short name for a search zone: "Lyon 7e", "Bordeaux"
    city: str
    postal_code: str
    district: str | None
    country_code: str
    lat: float
    lon: float


class PlaceList(BaseModel):
    data: list[PlaceOut]


RADIUS_KM = (1, 2, 5, 10, 25, 50, 100)
RadiusKm = Literal[1, 2, 5, 10, 25, 50, 100]


def _check_point(model: BaseModel, lat: float | None, lon: float | None) -> None:
    sent = model.model_fields_set
    if ("lat" in sent) != ("lon" in sent) or (lat is None) != (lon is None):
        raise ValueError("lat and lon go together")


class AddressIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, max_length=40)
    full_name: str = Field(min_length=1, max_length=100)
    line1: str = Field(min_length=1, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    postal_code: str = Field(min_length=1, max_length=20)
    city: str = Field(min_length=1, max_length=100)
    country_code: str = Field(default="FR", pattern=r"^[A-Z]{2}$")
    phone_e164: str | None = Field(default=None, pattern=r"^\+[1-9][0-9]{6,14}$")
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    is_default_shipping: bool = False

    @model_validator(mode="after")
    def _point(self) -> "AddressIn":
        _check_point(self, self.lat, self.lon)
        return self


class AddressPatch(BaseModel):
    """Only the fields sent change; `lat` and `lon` go together."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, max_length=40)
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    line1: str | None = Field(default=None, min_length=1, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    postal_code: str | None = Field(default=None, min_length=1, max_length=20)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    phone_e164: str | None = Field(default=None, pattern=r"^\+[1-9][0-9]{6,14}$")
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    is_default_shipping: bool | None = None

    @model_validator(mode="after")
    def _required(self) -> "AddressPatch":
        for name in ("full_name", "line1", "postal_code", "city", "country_code"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        _check_point(self, self.lat, self.lon)
        return self


class AddressOut(BaseModel):
    id: UUID
    label: str | None
    full_name: str
    line1: str
    line2: str | None
    postal_code: str
    city: str
    country_code: str
    phone_e164: str | None
    lat: float | None
    lon: float | None
    is_default_shipping: bool
    created_at: datetime


class AddressList(BaseModel):
    data: list[AddressOut]


class ZoneIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=40)
    place_name: str = Field(min_length=1, max_length=80)  # from /v1/geo: "Lyon 7e"
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radius_km: RadiusKm = 5
    is_default: bool = False


class ZonePatch(BaseModel):
    """A new place needs `place_name`, `lat` and `lon` together. `is_default` can only be
    set to true: another zone becomes the default by being chosen, never by unsetting."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=40)
    place_name: str | None = Field(default=None, min_length=1, max_length=80)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    radius_km: RadiusKm | None = None
    is_default: Literal[True] | None = None

    @model_validator(mode="after")
    def _place(self) -> "ZonePatch":
        place = {"place_name", "lat", "lon"} & self.model_fields_set
        if place and (
            place != {"place_name", "lat", "lon"} or None in (self.place_name, self.lat, self.lon)
        ):
            raise ValueError("place_name, lat and lon go together")
        for name in ("label", "radius_km", "is_default"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class ZoneOut(BaseModel):
    id: UUID
    label: str
    place_name: str
    lat: float
    lon: float
    radius_km: int
    is_default: bool


class ZoneList(BaseModel):
    data: list[ZoneOut]
