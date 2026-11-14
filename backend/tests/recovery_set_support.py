"""Synthetic-only helpers for the spec 074 tests.

Everything here is test data: a synthetic key generated with ``secrets`` at test time and tiny
fixture files. No real key, credential, database or recovery set is ever created or read.
"""

import json
import os
import secrets
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.recovery_set.cli import run
from app.recovery_set.format import KEY_PURPOSE

CREATED = "2026-11-14T00:00:00Z"
SET_ID = "11111111-1111-4111-8111-111111111111"


@dataclass
class SyntheticKey:
    path: Path
    key_id: str
    installation_id: str
    material: str
    created_at: str = CREATED

    def fingerprint(self):
        from app.recovery_set.key import KeyFile

        return KeyFile.model_validate(self.document()).fingerprint()

    def document(self):
        return {
            "schema_version": 1,
            "purpose": KEY_PURPOSE,
            "key_id": self.key_id,
            "installation_id": self.installation_id,
            "created_at": self.created_at,
            "material": self.material,
        }


def private_dir(path, mode=0o700):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, mode)
    return path


def write_private(path, data, mode=0o600):
    path = Path(path)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    os.chmod(path, mode)
    return path


def make_key(directory, *, installation_id=None, material=None, name="recovery.key"):
    directory = private_dir(directory)
    key = SyntheticKey(
        path=directory / name,
        key_id=str(uuid.uuid4()),
        installation_id=installation_id or str(uuid.uuid4()),
        material=material or secrets.token_hex(32),
    )
    write_private(key.path, json.dumps(key.document()))
    return key


@dataclass
class SyntheticSet:
    root: Path
    set_dir: Path
    root_id: str
    objects: list = field(default_factory=list)
    archive: bool = True


def make_set(root, *, archive=True, objects=3, dump=b"synthetic dump bytes"):
    root = private_dir(root)
    set_dir = private_dir(root / "set")
    write_private(set_dir / "database.dump", dump)
    root_id = str(uuid.uuid4())
    names = []
    if archive:
        arch = private_dir(set_dir / "archive")
        write_private(arch / ".archive.json", json.dumps({"schema_version": 1, "root_id": root_id}))
        write_private(arch / ".archive.lock", b"")
        for index in range(objects):
            name = f"{uuid.UUID(int=index + 1).hex}-v1.original"
            write_private(arch / name, f"synthetic original {index}".encode())
            names.append(name)
    return SyntheticSet(root, set_dir, root_id, names, archive)


def generate_args(synthetic, key, output, *, head=None, expect=None, installation=None, extra=()):
    from app.recovery_set.verify import verifier_chain

    return [
        "generate", "--set", str(synthetic.set_dir), "--output", str(output),
        "--recovery-key", str(key.path), "--expected-key-fingerprint", key.fingerprint(),
        "--installation-id", installation or key.installation_id,
        "--schema-head", head or verifier_chain()[-1],
        "--expect-archive", expect or ("present" if synthetic.archive else "absent"),
        *extra,
    ]  # fmt: skip


def verify_args(synthetic, key, manifest, *, head=None, expect=None, installation=None, extra=()):
    from app.recovery_set.verify import verifier_chain

    return [
        "verify", "--set", str(synthetic.set_dir), "--manifest", str(manifest),
        "--recovery-key", str(key.path), "--expected-key-fingerprint", key.fingerprint(),
        "--expected-installation-id", installation or key.installation_id,
        "--expected-schema-head", head or verifier_chain()[-1],
        "--expect-archive", expect or ("present" if synthetic.archive else "absent"),
        *extra,
    ]  # fmt: skip


def run_generate(synthetic, key, output, **kwargs):
    return run(generate_args(synthetic, key, output, **kwargs))


def run_verify(synthetic, key, manifest, **kwargs):
    return run(verify_args(synthetic, key, manifest, **kwargs))


import pytest

from app.recovery_set.format import canonical


@dataclass
class World:
    root: Path
    synthetic: SyntheticSet
    key: SyntheticKey
    out_dir: Path
    manifest: Path

    def verify(self, **kwargs):
        return run_verify(self.synthetic, self.key, self.manifest, **kwargs)

    def load(self):
        return json.loads(self.manifest.read_bytes())

    def rewrite(self, mutate, *, resign=True, key=None, raw=None):
        """Mutate the parsed envelope and write it back, canonical and re-signed by default."""
        document = self.load()
        mutate(document)
        signer = key or self.key
        if resign:
            document["mac"] = _mac(signer, document["payload"])
        data = raw(document) if raw else canonical(document)
        self.manifest.chmod(0o600)
        self.manifest.write_bytes(data)
        self.manifest.chmod(0o600)

    def hash(self):
        from app.recovery_set.format import manifest_hash

        return manifest_hash(self.load()["payload"])


def _mac(key, payload):
    from app.recovery_set.key import KeyFile

    return KeyFile.model_validate(key.document()).mac(payload)


def build_world(tmp_path, *, archive=True, objects=3, name="w"):
    root = private_dir(tmp_path / name)
    synthetic = make_set(root / "s", archive=archive, objects=objects)
    key = make_key(root / "k")
    out_dir = private_dir(root / "out")
    manifest = out_dir / "manifest.json"
    output, status = run_generate(synthetic, key, manifest)
    assert status == 0, output
    return World(root, synthetic, key, out_dir, manifest)


@pytest.fixture
def world(tmp_path):
    return build_world(tmp_path)


@pytest.fixture
def bare_world(tmp_path):
    return build_world(tmp_path, archive=False, name="bare")
