"""Purpose-separated authenticated metadata for supplied source withdrawals."""

import argparse
import hashlib
import hmac
import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.work_lifecycle import Contract, clock
from app.work_suppression_auth import Key, _tag, fingerprint, load_key
from app.work_suppression_file import canonical, read_json_file, write_json_file

DIGEST_DOMAIN = b"butler.synthetic.source-withdrawal-checkpoint.v1\n"
AUTH_DOMAIN = b"butler.synthetic.source-withdrawal-auth.v1\n"


class Entry(Contract):
    source_id: UUID
    receipt_id: UUID
    withdrawn_at: datetime

    @model_validator(mode="after")
    def valid(self):
        clock(self.withdrawn_at)
        return self


class Body(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["synthetic_source_withdrawal_checkpoint"] = (
        "synthetic_source_withdrawal_checkpoint"
    )
    export_id: UUID
    workspace_id: UUID
    exported_by: UUID
    source_database_oid: int = Field(strict=True, ge=1, le=4294967295)
    generated_at: datetime
    items: tuple[Entry, ...] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def valid(self):
        generated = clock(self.generated_at)
        sources = [item.source_id for item in self.items]
        if sources != sorted(set(sources)) or any(
            clock(item.withdrawn_at) > generated for item in self.items
        ):
            raise ValueError("Ordered unique nonfuture source decisions required")
        return self


def digest(body: Body):
    return hashlib.sha256(DIGEST_DOMAIN + canonical(body.model_dump(mode="json"))).hexdigest()


class Manifest(Contract):
    body: Body
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def valid(self):
        if (
            not hmac.compare_digest(self.digest, digest(self.body))
            or len(canonical(self.model_dump(mode="json"))) > 32768
        ):
            raise ValueError("Invalid source checkpoint digest/bound")
        return self


class Signed(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["synthetic_authenticated_source_withdrawals"] = (
        "synthetic_authenticated_source_withdrawals"
    )
    algorithm: Literal["HMAC-SHA256"] = "HMAC-SHA256"
    key_id: UUID
    key_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    manifest: Manifest
    mac: str = Field(pattern=r"^[a-f0-9]{64}$")


def _payload(manifest, key):
    return {
        "schema_version": 1,
        "mode": "synthetic_authenticated_source_withdrawals",
        "algorithm": "HMAC-SHA256",
        "key_id": str(key.key_id),
        "key_fingerprint": fingerprint(key),
        "manifest": manifest.model_dump(mode="json"),
    }


def sign(manifest: Manifest, key: Key):
    if (
        not isinstance(manifest, Manifest)
        or not isinstance(key, Key)
        or manifest.body.workspace_id != key.workspace_id
    ):
        raise ValueError("Matching typed source checkpoint and key required")
    payload = _payload(manifest, key)
    return Signed(**payload, mac=_tag(key, AUTH_DOMAIN, payload))


def write_signed(path, manifest, key):
    write_json_file(path, sign(manifest, key).model_dump(mode="json"))


def read_signed(path, key: Key, workspace: UUID):
    value = read_json_file(path)
    if (
        not isinstance(value, dict)
        or set(value) != set(Signed.model_fields)
        or type(value.get("schema_version")) is not int
    ):
        raise ValueError("Complete authenticated source checkpoint required")
    manifest = value.get("manifest")
    if (
        not isinstance(manifest, dict)
        or set(manifest) != set(Manifest.model_fields)
        or not isinstance(manifest.get("body"), dict)
        or set(manifest["body"]) != set(Body.model_fields)
        or type(manifest["body"].get("schema_version")) is not int
    ):
        raise ValueError("Complete source manifest header required")
    signed = Signed.model_validate(value)
    if (
        key.workspace_id != workspace
        or signed.manifest.body.workspace_id != workspace
        or signed.key_id != key.key_id
        or not hmac.compare_digest(signed.key_fingerprint, fingerprint(key))
    ):
        raise ValueError("Source checkpoint key/namespace mismatch")
    if not hmac.compare_digest(
        signed.mac, _tag(key, AUTH_DOMAIN, signed.model_dump(mode="json", exclude={"mac"}))
    ):
        raise ValueError("Source checkpoint authentication failed")
    return signed.manifest


def require_checkpoint(manifest: Manifest, expected_hash: str):
    if (
        not isinstance(manifest, Manifest)
        or not isinstance(expected_hash, str)
        or not re.fullmatch(r"[a-f0-9]{64}", expected_hash)
        or not hmac.compare_digest(manifest.digest, expected_hash)
    ):
        raise ValueError("Independently trusted source checkpoint required")
    return {"mode": "independently_pinned_source_withdrawals", "manifest_hash": expected_hash}


def checkpoint(manifest, key):
    return {
        "schema_version": 1,
        "mode": "synthetic_source_withdrawal_export_checkpoint",
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
        "independent_retention_verified": False,
        "latest_completeness_verified": False,
        "recovery_complete": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Offline source-checkpoint verification; no database configuration required"
    )
    parser.add_argument("command", choices=["verify"])
    parser.add_argument("--workspace", required=True, type=UUID)
    parser.add_argument("--recovery-key", required=True)
    parser.add_argument("--expected-key-fingerprint", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--expected-manifest-hash", required=True)
    args = parser.parse_args()
    try:
        key = load_key(args.recovery_key, args.expected_key_fingerprint, args.workspace)
        manifest = read_signed(args.manifest, key, args.workspace)
        context = require_checkpoint(manifest, args.expected_manifest_hash)
        result = {
            "mode": "synthetic_source_checkpoint_authenticated",
            "checkpoint": context,
            "authentication": {"key_id": str(key.key_id), "key_fingerprint": fingerprint(key)},
            "workspace_id": str(args.workspace),
            "export_id": str(manifest.body.export_id),
            "item_count": len(manifest.body.items),
            "latest_completeness_verified": False,
            "recovery_complete": False,
        }
    except (ValueError, OSError):
        parser.exit(
            1,
            "Source checkpoint verification failed; independently review key, namespace and retained checkpoint\n",
        )
    print(canonical(result).decode())


if __name__ == "__main__":
    main()
