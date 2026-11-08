"""Offline workspace recovery authentication; no encryption or latest-ledger proof."""

import argparse
import hmac
import re
import secrets
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, SecretStr, field_validator, model_validator

from app.work_lifecycle import Contract, clock
from app.work_suppression_file import (
    Manifest,
    canonical,
    manifest_from_value,
    read_json_file,
    write_json_file,
)

KEY_DOMAIN = b"butler.synthetic.work-recovery-key-fingerprint.v1\n"
MANIFEST_DOMAIN = b"butler.synthetic.work-suppression-auth.v2\n"


class Key(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["synthetic_work_suppression_key"] = "synthetic_work_suppression_key"
    key_id: UUID
    workspace_id: UUID
    created_at: datetime
    material: SecretStr

    @field_validator("material")
    @classmethod
    def material_valid(cls, value):
        if not re.fullmatch(r"[a-f0-9]{64}", value.get_secret_value()):
            raise ValueError("Invalid recovery key material")
        return value

    @model_validator(mode="after")
    def valid(self):
        clock(self.created_at)
        return self


def generate_key(workspace: UUID):
    if not isinstance(workspace, UUID):
        raise TypeError("Typed workspace required")
    return Key(
        key_id=uuid4(),
        workspace_id=workspace,
        created_at=datetime.now(UTC),
        material=secrets.token_hex(32),
    )


def _tag(key, domain, value):
    return hmac.new(
        bytes.fromhex(key.material.get_secret_value()),
        domain + canonical(value),
        digestmod="sha256",
    ).hexdigest()


def fingerprint(key: Key):
    return _tag(key, KEY_DOMAIN, key.model_dump(mode="json", exclude={"material"}))


def write_key(path, key: Key):
    if not isinstance(key, Key):
        raise TypeError("Typed key required")
    # Deliberate secret serialization only into the protected new file; never output.
    write_json_file(
        path,
        {**key.model_dump(mode="json"), "material": key.material.get_secret_value()},
        max_bytes=2048,
    )


def load_key(path, expected_fingerprint: str, workspace: UUID):
    if not re.fullmatch(r"[a-f0-9]{64}", expected_fingerprint):
        raise ValueError("Explicit independently trusted fingerprint required")
    value = read_json_file(path, max_bytes=2048)
    if (
        not isinstance(value, dict)
        or set(value) != set(Key.model_fields)
        or type(value.get("schema_version")) is not int
    ):
        raise ValueError("Complete recovery key header required")
    key = Key.model_validate(value)
    if key.workspace_id != workspace or not hmac.compare_digest(
        fingerprint(key), expected_fingerprint
    ):
        raise ValueError("Recovery key namespace or trusted fingerprint mismatch")
    return key


class Payload(Contract):
    schema_version: Literal[2] = 2
    mode: Literal["synthetic_work_authenticated_suppression"] = (
        "synthetic_work_authenticated_suppression"
    )
    algorithm: Literal["HMAC-SHA256"] = "HMAC-SHA256"
    key_id: UUID
    key_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    manifest: Manifest


class Signed(Payload):
    mac: str = Field(pattern=r"^[a-f0-9]{64}$")


def sign(manifest: Manifest, key: Key):
    if (
        not isinstance(manifest, Manifest)
        or not isinstance(key, Key)
        or key.workspace_id != manifest.body.workspace_id
    ):
        raise ValueError("Matching typed key and manifest required")
    payload = Payload(key_id=key.key_id, key_fingerprint=fingerprint(key), manifest=manifest)
    return Signed(
        **payload.model_dump(), mac=_tag(key, MANIFEST_DOMAIN, payload.model_dump(mode="json"))
    )


def write_signed(path, manifest: Manifest, key: Key):
    write_json_file(path, sign(manifest, key).model_dump(mode="json"))


def read_signed(path, key: Key, workspace: UUID):
    value = read_json_file(path)
    if (
        not isinstance(value, dict)
        or set(value) != set(Signed.model_fields)
        or type(value.get("schema_version")) is not int
    ):
        raise ValueError("Authenticated version-2 manifest required; re-export legacy files")
    manifest_from_value(value["manifest"])
    signed = Signed.model_validate(value)
    if (
        key.workspace_id != workspace
        or signed.manifest.body.workspace_id != workspace
        or signed.key_id != key.key_id
        or not hmac.compare_digest(signed.key_fingerprint, fingerprint(key))
    ):
        raise ValueError("Authenticated key identity/namespace mismatch")
    expected = _tag(key, MANIFEST_DOMAIN, signed.model_dump(mode="json", exclude={"mac"}))
    if not hmac.compare_digest(signed.mac, expected):
        raise ValueError("Manifest authentication failed")
    return signed.manifest


def require_checkpoint(manifest: Manifest, expected_hash: str):
    """Compare an explicitly retained source hash, never discover trust from input."""
    if (
        not isinstance(expected_hash, str)
        or not re.fullmatch(r"[a-f0-9]{64}", expected_hash)
        or not hmac.compare_digest(manifest.digest, expected_hash)
    ):
        raise ValueError("Independently trusted manifest checkpoint required")
    return {"mode": "independently_pinned_manifest", "manifest_hash": expected_hash}


def checkpoint(manifest: Manifest, key: Key):
    """Public source export record; retention/trust must be established separately."""
    return {
        "schema_version": 1,
        "mode": "synthetic_work_recovery_checkpoint",
        "workspace_id": str(manifest.body.workspace_id),
        "export_id": str(manifest.body.export_id),
        "generated_at": manifest.body.generated_at.isoformat(),
        "manifest_hash": manifest.digest,
        "item_count": len(manifest.body.items),
        "authentication": {
            "mode": "hmac_sha256",
            "key_id": str(key.key_id),
            "key_fingerprint": fingerprint(key),
        },
        "recovery_complete": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate")
    generate.add_argument("--workspace", required=True, type=UUID)
    generate.add_argument("--output", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--workspace", required=True, type=UUID)
    verify.add_argument("--recovery-key", required=True)
    verify.add_argument("--expected-key-fingerprint", required=True)
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--expected-manifest-hash", required=True)
    args = parser.parse_args()
    try:
        if args.command == "generate":
            key = generate_key(args.workspace)
            write_key(args.output, key)
            result = {
                "mode": "synthetic_work_recovery_key_created",
                "key_id": str(key.key_id),
                "workspace_id": str(key.workspace_id),
                "fingerprint": fingerprint(key),
                "material_returned": False,
                "independent_recovery_proven": False,
            }
        else:
            key = load_key(args.recovery_key, args.expected_key_fingerprint, args.workspace)
            manifest = read_signed(args.manifest, key, args.workspace)
            context = require_checkpoint(manifest, args.expected_manifest_hash)
            result = {
                "mode": "synthetic_work_manifest_authenticated",
                "checkpoint": context,
                "workspace_id": str(args.workspace),
                "key_id": str(key.key_id),
                "key_fingerprint": fingerprint(key),
                "manifest_hash": manifest.digest,
                "export_id": str(manifest.body.export_id),
                "generated_at": manifest.body.generated_at.isoformat(),
                "item_count": len(manifest.body.items),
                "recovery_complete": False,
            }
    except (ValueError, OSError):
        parser.exit(
            1,
            "Recovery authentication operation failed; inspect protected files and independently trusted anchor before retry\n",
        )
    print(canonical(result).decode())


if __name__ == "__main__":
    main()
