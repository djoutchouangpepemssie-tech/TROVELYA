import pytest
from pydantic import ValidationError

from tests.conftest import make_settings


def test_missing_secret_key_fails() -> None:
    with pytest.raises(ValidationError):
        make_settings(secret_key=None)


def test_short_secret_key_fails() -> None:
    with pytest.raises(ValidationError):
        make_settings(secret_key="too-short")


def test_unknown_env_fails() -> None:
    with pytest.raises(ValidationError):
        make_settings(env="prod")


def test_secret_key_is_not_printed() -> None:
    assert "s" * 64 not in repr(make_settings())


@pytest.mark.parametrize(
    "given",
    [
        "postgresql://u:p@host:5432/db",
        "postgres://u:p@host:5432/db",
        "postgresql+asyncpg://u:p@host:5432/db",
    ],
)
def test_database_url_uses_asyncpg_driver(given: str) -> None:
    """Railway provides postgresql:// URLs; the application always needs the asyncpg driver."""
    assert make_settings(database_url=given).database_url == "postgresql+asyncpg://u:p@host:5432/db"


def test_database_url_rejects_other_schemes() -> None:
    with pytest.raises(ValidationError):
        make_settings(database_url="mysql://u:p@host/db")


def test_short_proxy_secret_fails() -> None:
    with pytest.raises(ValidationError):
        make_settings(proxy_shared_secret="too-short")


def test_proxy_secret_is_not_printed() -> None:
    assert "p" * 48 not in repr(make_settings())


def test_resend_requires_an_api_key() -> None:
    with pytest.raises(ValidationError, match="EMAIL_API_KEY"):
        make_settings(email_provider="resend")
    assert make_settings(email_provider="resend", email_api_key="re_x").email_provider == "resend"


def test_short_field_encryption_key_fails() -> None:
    with pytest.raises(ValidationError):
        make_settings(field_encryption_key="too-short")


def test_google_client_id_and_secret_go_together() -> None:
    with pytest.raises(ValidationError):
        make_settings(oauth_google_client_id="id.apps.googleusercontent.com")
    settings = make_settings(
        oauth_google_client_id="id.apps.googleusercontent.com",
        oauth_google_client_secret="gocspx-test-secret",
    )
    assert "gocspx-test-secret" not in repr(settings)
