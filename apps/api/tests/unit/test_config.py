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
