"""Application-level encryption (AES-256-GCM, section 13.2) for job payloads and exports."""

import pytest

from trovelya.shared.crypto import SealError, derive_key, open_sealed, seal

SECRET = "f" * 64


def test_seal_roundtrip() -> None:
    key = derive_key(SECRET, purpose="email")
    blob = seal(b"bonjour", key=key, aad=b"ctx")
    assert b"bonjour" not in blob
    assert open_sealed(blob, key=key, aad=b"ctx") == b"bonjour"


def test_seal_is_randomised() -> None:
    key = derive_key(SECRET, purpose="email")
    assert seal(b"x", key=key, aad=b"") != seal(b"x", key=key, aad=b"")


def test_seal_wrong_aad_fails() -> None:
    key = derive_key(SECRET, purpose="email")
    with pytest.raises(SealError):
        open_sealed(seal(b"x", key=key, aad=b"email"), key=key, aad=b"export")


def test_seal_tampered_fails() -> None:
    key = derive_key(SECRET, purpose="email")
    blob = bytearray(seal(b"x", key=key, aad=b""))
    blob[-1] ^= 1
    with pytest.raises(SealError):
        open_sealed(bytes(blob), key=key, aad=b"")


def test_seal_wrong_key_or_truncated_fails() -> None:
    blob = seal(b"x", key=derive_key(SECRET, purpose="email"), aad=b"")
    with pytest.raises(SealError):
        open_sealed(blob, key=derive_key("g" * 64, purpose="email"), aad=b"")
    with pytest.raises(SealError):
        open_sealed(blob[:10], key=derive_key(SECRET, purpose="email"), aad=b"")


def test_derived_keys_depend_on_purpose_and_secret() -> None:
    assert len(derive_key(SECRET, purpose="email")) == 32
    assert derive_key(SECRET, purpose="email") == derive_key(SECRET, purpose="email")
    assert derive_key(SECRET, purpose="email") != derive_key(SECRET, purpose="export")
    assert derive_key(SECRET, purpose="email") != derive_key("g" * 64, purpose="email")
