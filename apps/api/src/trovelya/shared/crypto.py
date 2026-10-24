"""Application-level encryption (section 13.2): AES-256-GCM with keys derived per purpose.

Used for values that must leave PostgreSQL's protection or be stored more strictly than the
host's disk encryption: e-mail jobs in Redis (they hold an address and sometimes a sign-in
link), GDPR export archives (ADR-0016), and later tax identifiers (P4).

`FIELD_ENCRYPTION_KEY` is a random secret of at least 32 characters; each purpose gets its own
256-bit key through HKDF-SHA256, so a key leaked from one use does not open another.
A sealed blob is `nonce (12 bytes) ‖ ciphertext ‖ tag`.
"""

import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

KEY_BYTES = 32
NONCE_BYTES = 12


class SealError(Exception):
    """The blob is not ours: wrong key, wrong context, truncated or tampered with."""


def derive_key(secret: str, *, purpose: str) -> bytes:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_BYTES,
        salt=None,
        info=f"trovelya:{purpose}".encode(),
    )
    return hkdf.derive(secret.encode())


def seal(plaintext: bytes, *, key: bytes, aad: bytes) -> bytes:
    nonce = secrets.token_bytes(NONCE_BYTES)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def open_sealed(blob: bytes, *, key: bytes, aad: bytes) -> bytes:
    if len(blob) <= NONCE_BYTES:
        raise SealError("sealed blob too short")
    try:
        return AESGCM(key).decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:], aad)
    except InvalidTag as exc:
        raise SealError("sealed blob rejected") from exc
