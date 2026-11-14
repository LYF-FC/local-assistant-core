"""Recovery key file, namespace separation, keyed fingerprint and MAC (spec 074 sections 4.2, 6)."""

import hashlib
import hmac
import re

from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError, field_validator

from app.recovery_set.format import (
    FINGERPRINT_DOMAIN,
    KEY_PURPOSE,
    MAC_DOMAIN,
    CodedError,
    Limits,
    canonical,
    parse_json,
    valid_timestamp,
    valid_uuid,
)
from app.recovery_set.fsset import read_protected_file


class KeyFile(BaseModel):
    """Closed key file model. The material is a masked secret and never leaves this module."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: int
    purpose: str
    key_id: str
    installation_id: str
    created_at: str
    material: SecretStr

    @field_validator("schema_version")
    @classmethod
    def _version(cls, value):
        if value != 1:
            raise ValueError("schema version")
        return value

    @field_validator("key_id", "installation_id")
    @classmethod
    def _uuid(cls, value):
        if not valid_uuid(value):
            raise ValueError("uuid")
        return value

    @field_validator("created_at")
    @classmethod
    def _created(cls, value):
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value) or (
            not valid_timestamp(value)
        ):
            raise ValueError("timestamp")
        return value

    @field_validator("material")
    @classmethod
    def _material(cls, value):
        if not re.fullmatch(r"[a-f0-9]{64}", value.get_secret_value()):
            raise ValueError("key material")
        return value

    def __repr__(self):
        return "KeyFile(<masked>)"

    __str__ = __repr__

    def _secret(self):
        return bytes.fromhex(self.material.get_secret_value())

    def public_identity(self):
        return {
            "key_id": self.key_id,
            "purpose": self.purpose,
            "installation_id": self.installation_id,
            "created_at": self.created_at,
        }

    def fingerprint(self):
        """Keyed tag over the public identity fields, keyed by the secret (not an unkeyed hash)."""
        return hmac.new(
            self._secret(), FINGERPRINT_DOMAIN + canonical(self.public_identity()), hashlib.sha256
        ).hexdigest()

    def mac(self, payload_value):
        return hmac.new(
            self._secret(), MAC_DOMAIN + canonical(payload_value), hashlib.sha256
        ).hexdigest()


def load_key(path, limits: Limits):
    """Protected read, namespace check and structure. Never accepts the secret by argument."""
    data = read_protected_file(
        path,
        max_bytes=limits.key_file_bytes,
        unsafe_code="key_file_unsafe",
        too_large_code="key_file_unsafe",
        any_group_other_bit=True,
        require_owner=True,
    )
    try:
        value = parse_json(data, "key_file_malformed", "key_file_malformed")
    except CodedError as error:
        raise CodedError("key_file_malformed") from error
    if not isinstance(value, dict):
        raise CodedError("key_file_malformed")
    if value.get("purpose") != KEY_PURPOSE:
        raise CodedError("key_namespace_mismatch")
    try:
        return KeyFile.model_validate(value)
    except ValidationError as error:
        raise CodedError("key_file_malformed") from error


def check_fingerprint(key: KeyFile, expected_fingerprint):
    if not hmac.compare_digest(key.fingerprint().encode(), expected_fingerprint.encode()):
        raise CodedError("key_fingerprint_mismatch")


def verify_mac(key: KeyFile, envelope, payload_value):
    """Authenticity stage 3 checks after the key file itself is trusted (spec 7.2 item 3)."""
    declared = envelope.payload.body.installation.installation_id
    if not hmac.compare_digest(key.installation_id.encode(), declared.encode()):
        raise CodedError("key_installation_mismatch")
    payload = envelope.payload
    if payload.key_id != key.key_id or not hmac.compare_digest(
        payload.key_fingerprint.encode(), key.fingerprint().encode()
    ):
        raise CodedError("manifest_key_reference_mismatch")
    if not hmac.compare_digest(envelope.mac.encode(), key.mac(payload_value).encode()):
        raise CodedError("manifest_authentication_failed")
