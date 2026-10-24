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
