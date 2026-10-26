"""Application settings, read from the environment (docs/CAHIER_DES_CHARGES.md section 5.8)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "preview", "staging", "production", "test"]

MIN_SECRET_KEY_LENGTH = 64
MIN_PROXY_SECRET_LENGTH = 32
MIN_FIELD_KEY_LENGTH = 32
EmailProvider = Literal["smtp", "resend", "fake"]
GeocoderProvider = Literal["geoplateforme", "fake"]
StorageProvider = Literal["s3", "memory"]


def asyncpg_url(url: str) -> str:
    """Hosting platforms (Railway) give postgresql:// URLs: always use the asyncpg driver."""
    scheme, separator, rest = url.partition("://")
    if not separator or scheme not in {"postgresql", "postgres", "postgresql+asyncpg"}:
        raise ValueError("database_url must be a PostgreSQL URL")
    return f"postgresql+asyncpg://{rest}"


class Settings(BaseSettings):
    """Validated at startup: a missing or invalid required variable stops the process."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    env: Environment
    database_url: str
    redis_url: str
    secret_key: SecretStr = Field(min_length=MIN_SECRET_KEY_LENGTH)
    # Shared with the web relay; authenticates the client IP it forwards (ADR-0015).
    proxy_shared_secret: SecretStr = Field(min_length=MIN_PROXY_SECRET_LENGTH)
    # Application-level encryption (shared/crypto.py): e-mail jobs, GDPR exports.
    field_encryption_key: SecretStr = Field(min_length=MIN_FIELD_KEY_LENGTH)
    # Transactional e-mail (ADR-0017): smtp (Mailpit), resend (staging), fake (tests).
    email_provider: EmailProvider = "fake"
    email_api_key: SecretStr | None = None
    email_from: str = "TROVÉLYA <no-reply@localhost>"
    smtp_url: str = "smtp://localhost:1025"
    # Cloudflare Turnstile on sign-in requests (section 13.1); off while unset.
    turnstile_secret_key: SecretStr | None = None
    # Sign-in with Google (P1-T03): OAuth client of the Google Cloud project; off while unset.
    oauth_google_client_id: str | None = None
    oauth_google_client_secret: SecretStr | None = None
    # Sign in with Apple (P1-T03b): Services ID, team, key id and `.p8` key; off while unset.
    oauth_apple_client_id: str | None = None
    oauth_apple_team_id: str | None = None
    oauth_apple_key_id: str | None = None
    oauth_apple_private_key: SecretStr | None = None
    web_origin: str
    admin_origin: str
    # Geocoding (P1-T06a, E10): IGN Géoplateforme; "fake" for tests and offline development.
    geocoder_provider: GeocoderProvider = "geoplateforme"
    # Passkeys (P1-T04): relying party; defaults to the web origin's host and the web origin.
    webauthn_rp_id: str | None = None
    webauthn_rp_name: str = "TROVÉLYA"
    webauthn_origins: list[str] = Field(default_factory=list[str])
    # Object storage (ADR-0019): s3 = Cloudflare R2 (EU jurisdiction) on Railway, Garage
    # locally and in tests; memory for unit tests and environments without storage yet.
    storage_provider: StorageProvider = "memory"
    storage_endpoint: str | None = None
    storage_region: str = "auto"  # R2 takes "auto"; Garage "garage"
    storage_access_key_id: SecretStr | None = None
    storage_secret_access_key: SecretStr | None = None
    storage_bucket_originals: str = "trovelya-originals"
    storage_bucket_variants: str = "trovelya-variants"
    # Public base URL of the variants bucket (r2.dev on staging, media.trovelya.com later).
    media_public_url: str | None = None
    sentry_dsn: str | None = None
    otel_exporter_otlp_endpoint: str | None = None
    feature_flags_default: dict[str, bool] = Field(default_factory=dict[str, bool])
    rate_limit_anonymous_per_minute: int = Field(default=120, ge=1)  # section 11.4
    rate_limit_user_per_minute: int = Field(default=600, ge=1)  # section 11.4
    # Sessions (section 13.2, P1 plan Q9): absolute lifetime, inactivity, staff sessions.
    session_ttl_days: int = Field(default=30, ge=1)
    session_idle_days: int = Field(default=14, ge=1)
    admin_session_ttl_hours: int = Field(default=12, ge=1)

    @model_validator(mode="after")
    def _resend_needs_a_key(self) -> "Settings":
        if self.email_provider == "resend" and self.email_api_key is None:
            raise ValueError("EMAIL_API_KEY is required when EMAIL_PROVIDER=resend")
        return self

    @model_validator(mode="after")
    def _google_needs_both(self) -> "Settings":
        if (self.oauth_google_client_id is None) != (self.oauth_google_client_secret is None):
            raise ValueError("OAUTH_GOOGLE_CLIENT_ID and OAUTH_GOOGLE_CLIENT_SECRET go together")
        return self

    @model_validator(mode="after")
    def _apple_needs_all(self) -> "Settings":
        values = (
            self.oauth_apple_client_id,
            self.oauth_apple_team_id,
            self.oauth_apple_key_id,
            self.oauth_apple_private_key,
        )
        if any(v is None for v in values) and any(v is not None for v in values):
            raise ValueError(
                "OAUTH_APPLE_CLIENT_ID, _TEAM_ID, _KEY_ID and _PRIVATE_KEY go together"
            )
        return self

    @model_validator(mode="after")
    def _s3_needs_endpoint_and_keys(self) -> "Settings":
        values = (self.storage_endpoint, self.storage_access_key_id, self.storage_secret_access_key)
        if self.storage_provider == "s3" and any(v is None for v in values):
            raise ValueError(
                "STORAGE_ENDPOINT, STORAGE_ACCESS_KEY_ID and STORAGE_SECRET_ACCESS_KEY are"
                " required when STORAGE_PROVIDER=s3"
            )
        return self

    @field_validator("database_url")
    @classmethod
    def _use_asyncpg_driver(cls, url: str) -> str:
        return asyncpg_url(url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # values come from the environment
