"""A software authenticator for tests: real WebAuthn responses signed with an EC P-256 key."""

import hashlib
import json
import secrets
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import bytes_to_base64url, encode_cbor

FLAG_UP = 0x01
FLAG_UV = 0x04
FLAG_AT = 0x40


def _client_data(kind: str, challenge: str, origin: str) -> bytes:
    data = {"type": kind, "challenge": challenge, "origin": origin, "crossOrigin": False}
    return json.dumps(data, separators=(",", ":")).encode()


class SoftAuthenticator:
    """One discoverable credential (passkey) for one user."""

    def __init__(self, *, rp_id: str, origin: str, user_handle: bytes) -> None:
        self.rp_id = rp_id
        self.origin = origin
        self.user_handle = user_handle
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = secrets.token_bytes(16)
        self.sign_count = 0

    @property
    def id(self) -> str:
        return bytes_to_base64url(self.credential_id)

    def _cose_key(self) -> bytes:
        numbers = self.key.public_key().public_numbers()
        return encode_cbor(
            {
                1: 2,  # kty: EC2
                3: -7,  # alg: ES256
                -1: 1,  # crv: P-256
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )

    def _auth_data(self, flags: int, *, rp_id: str | None = None, attested: bool = False) -> bytes:
        data = hashlib.sha256((rp_id or self.rp_id).encode()).digest()
        data += bytes([flags]) + self.sign_count.to_bytes(4, "big")
        if attested:
            data += bytes(16)  # AAGUID
            data += len(self.credential_id).to_bytes(2, "big") + self.credential_id
            data += self._cose_key()
        return data

    def register(
        self, options: dict[str, Any], *, origin: str | None = None, rp_id: str | None = None
    ) -> dict[str, Any]:
        """navigator.credentials.create() answer for these options (attestation 'none')."""
        client_data = _client_data("webauthn.create", options["challenge"], origin or self.origin)
        auth_data = self._auth_data(FLAG_UP | FLAG_UV | FLAG_AT, rp_id=rp_id, attested=True)
        attestation = encode_cbor({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": self.id,
            "rawId": self.id,
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "attestationObject": bytes_to_base64url(attestation),
                "transports": ["internal"],
            },
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        }

    def assert_(
        self,
        options: dict[str, Any],
        *,
        origin: str | None = None,
        sign_count: int | None = None,
    ) -> dict[str, Any]:
        """navigator.credentials.get() answer for these options."""
        self.sign_count = self.sign_count + 1 if sign_count is None else sign_count
        client_data = _client_data("webauthn.get", options["challenge"], origin or self.origin)
        auth_data = self._auth_data(FLAG_UP | FLAG_UV)
        signed = auth_data + hashlib.sha256(client_data).digest()
        signature = self.key.sign(signed, ec.ECDSA(hashes.SHA256()))
        return {
            "id": self.id,
            "rawId": self.id,
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "authenticatorData": bytes_to_base64url(auth_data),
                "signature": bytes_to_base64url(signature),
                "userHandle": bytes_to_base64url(self.user_handle),
            },
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        }
