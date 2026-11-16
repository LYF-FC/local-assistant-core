"""Synthetic-only helpers for the spec 074 tests.

Everything here is test data: a synthetic key generated with ``secrets`` at test time and tiny
fixture files. No real key, credential, database or recovery set is ever created or read.
"""

import builtins
import collections
import contextlib
import io
import json
import os
import secrets
import sys
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


class AccessAttempted(Exception):
    pass


FILE_ACCESS_NAMES = (
    "open",
    "stat",
    "lstat",
    "fstat",
    "scandir",
    "listdir",
    "readlink",
    "access",
    "read",
)


@contextlib.contextmanager
def file_access_guards(*, raising):
    """Count (and optionally refuse) filesystem access entry points while a block runs.

    Patches ``os.open/stat/lstat/fstat/scandir/listdir/readlink/access/read`` and
    ``builtins.open``/``io.open``. It is installed by the caller after fixture setup, so setup is
    not blocked and import-time activity is not covered. References bound before installation
    (for example ``from os import open``) would not be seen; the controls below show the
    implementation reaches the patched attributes.
    """
    counts, origins, calls = collections.Counter(), collections.Counter(), []

    def make(kind, real):
        def guard(*args, **kwargs):
            counts[kind] += 1
            frames, frame = [], sys._getframe(1)
            while frame is not None:  # in memory only: no traceback or source formatting here
                code = frame.f_code
                frames.append((code.co_filename, code.co_name, frame.f_lineno))
                frame = frame.f_back
            if any("/app/recovery_set/" in name.replace("\\", "/") for name, _, _ in frames):
                origins[kind] += 1
            first = args[0] if args else None
            if isinstance(first, bytes):
                first = os.fsdecode(first)
            elif isinstance(first, os.PathLike):
                first = os.fspath(first)
            calls.append((kind, first if isinstance(first, str) else None, frames))
            if raising:
                raise AccessAttempted(kind)
            return real(*args, **kwargs)

        return guard

    with pytest.MonkeyPatch.context() as patch:
        for name in FILE_ACCESS_NAMES:
            patch.setattr(os, name, make(f"os.{name}", getattr(os, name)))
        for module in (builtins, io):
            patch.setattr(module, "open", make(f"{module.__name__}.open", module.open))
        yield counts, origins, calls


def describe_calls(calls, depth=10):
    """Report recorded calls (after the patches are removed): kind, path, innermost frames."""
    lines = []
    for kind, path, frames in calls:
        where = " <- ".join(
            f"{name.rsplit('/', 2)[-1]}:{func}:{line}" for name, func, line in frames[:depth]
        )
        lines.append(f"{kind} {path!r}: {where}")
    return "\n".join(lines)
