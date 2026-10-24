"""Application settings, read from the environment (docs/CAHIER_DES_CHARGES.md section 5.8)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "preview", "staging", "production", "test"]

MIN_SECRET_KEY_LENGTH = 64


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
    web_origin: str
    admin_origin: str
    sentry_dsn: str | None = None
    otel_exporter_otlp_endpoint: str | None = None
    feature_flags_default: dict[str, bool] = Field(default_factory=dict[str, bool])
    rate_limit_anonymous_per_minute: int = Field(default=120, ge=1)  # section 11.4

    @field_validator("database_url")
    @classmethod
    def _use_asyncpg_driver(cls, url: str) -> str:
        return asyncpg_url(url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # values come from the environment
