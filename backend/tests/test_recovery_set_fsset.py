# ruff: noqa: F811
"""Spec 074 B020 to B023: closed-set enumeration, invariants, limits (T2 to T7, T35, T36, T49,
T50, T52). All data is synthetic; limits are exercised with injected test limits only."""

import builtins
import io
import os
import socket
import stat
import subprocess
import sys
import uuid
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from recovery_set_support import (  # noqa: F401
    SyntheticSet,
    build_world,
    generate_args,
    make_key,
    make_set,
    private_dir,
    run_generate,
    verify_args,
    world,
    write_private,
)

from app.recovery_set import fsset
from app.recovery_set.cli import GENERATE_OPTIONS, VERIFY_FLAGS, VERIFY_OPTIONS, parse_trust, run
from app.recovery_set.format import Limits
from app.recovery_set.generate import generate
from app.recovery_set.publish import InjectedFaults
from app.recovery_set.verify import verify


def reasons(output):
    return output["reasons"]


def fresh(world, name):
    return build_world(world.root.parent / name)


def objects(world):
    return sorted(world.synthetic.set_dir.joinpath("archive").glob("*.original"))


def test_t2_missing_members(world):
    (world.synthetic.set_dir / "database.dump").unlink()
    out = world.verify()[0]
    assert reasons(out) == ["set_member_missing"]
    assert out["integrity"] == "integrity_invalid" and out["authenticity"] == "authenticity_valid"
    other = fresh(world, "o")
    objects(other)[0].unlink()
    assert reasons(other.verify()[0]) == ["set_member_missing"]


def test_t3_unexpected_files_and_directories(world):
    write_private(world.synthetic.set_dir / "notes.txt", b"x")
    assert reasons(world.verify()[0]) == ["set_member_unexpected"]
    other = fresh(world, "d")
    private_dir(other.synthetic.set_dir / "extra")
    assert reasons(other.verify()[0]) == ["set_directory_unexpected"]
    nested = fresh(world, "n")
    private_dir(nested.synthetic.set_dir / "archive" / "nested")
    assert reasons(nested.verify()[0]) == ["set_directory_unexpected"]
    listed = fresh(world, "l")  # an allowlisted name that the manifest does not list
    write_private(listed.synthetic.set_dir / "archive" / f"{uuid.uuid4().hex}-v1.original", b"x")
    assert reasons(listed.verify()[0]) == ["set_member_unexpected"]
    named = fresh(world, "p")  # a stale temporary inside SET is a failure, not a note
    write_private(named.synthetic.set_dir / ".recovery-set-tmp-abc", b"x")
    out = named.verify()[0]
    assert reasons(out) == ["set_member_unexpected"] and out["notes"] == []


def test_t4_size_mismatch(world):
    path = world.synthetic.set_dir / "database.dump"
    path.write_bytes(path.read_bytes()[:-1])
    assert reasons(world.verify()[0]) == ["set_member_size_mismatch"]
    other = fresh(world, "e")
    with open(other.synthetic.set_dir / "database.dump", "ab") as stream:
        stream.write(b"+")
    assert reasons(other.verify()[0]) == ["set_member_size_mismatch"]


def test_t5_hash_mismatch_with_unchanged_size(world):
    path = world.synthetic.set_dir / "database.dump"
    data = bytearray(path.read_bytes())
    data[0] ^= 1
    path.write_bytes(bytes(data))
    out = world.verify()[0]
    assert reasons(out) == ["set_member_hash_mismatch"] and out["integrity"] == "integrity_invalid"
    assert "verified_references" not in out


def test_archive_marker_must_match_declared_root(world):
    other_root = f'{{"schema_version": 1, "root_id": "{uuid.uuid4()}"}}'
    marker = world.synthetic.set_dir / "archive" / ".archive.json"
    assert len(other_root) == len(marker.read_text())
    marker.write_text(other_root)  # changing the marker alone is a hash mismatch
    assert reasons(world.verify()[0]) == ["set_member_hash_mismatch"]
    other = fresh(world, "r")
    (other.synthetic.set_dir / "archive" / ".archive.json").write_text(other_root)
    other.manifest.unlink()
    assert run_generate(other.synthetic, other.key, other.manifest)[1] == 0
    assert other.verify()[1] == 0  # a consistent marker and manifest verify
    # a manifest that declares a different root than the (hash-matching) marker is refused
    other.rewrite(lambda d: d["payload"]["body"]["archive"].update(root_id=str(uuid.uuid4())))
    assert reasons(other.verify()[0]) == ["archive_marker_mismatch"]


def test_t6_symlink_members_and_directories(world):
    target = world.root / "target"
    target.write_bytes(b"synthetic original 0")
    victim = objects(world)[0]
    victim.unlink()
    victim.symlink_to(target)
    assert reasons(world.verify()[0]) == ["set_member_symlink"]
    other = fresh(world, "link")
    link = other.root / "set-link"
    link.symlink_to(other.synthetic.set_dir)
    linked = replace(other.synthetic, set_dir=link)
    assert reasons(run(verify_args(linked, other.key, other.manifest))[0]) == ["set_member_symlink"]
    arch = fresh(world, "archlink")
    real = arch.synthetic.set_dir / "archive"
    moved = arch.root / "archive-real"
    real.rename(moved)
    real.symlink_to(moved)
    assert reasons(arch.verify()[0]) == ["set_member_symlink"]


def test_t6_special_files_and_hard_links(world):
    """Unprivileged T6 cases: FIFO, socket, hard-linked member, non-directory SET root.

    The privilege-dependent device-node case is a separate test below, so a missing privilege
    can never suppress these assertions.
    """
    victim = objects(world)[0]
    victim.unlink()
    os.mkfifo(victim)
    assert reasons(world.verify()[0]) == ["set_member_not_regular"]
    sock = fresh(world, "sock")
    victim = objects(sock)[0]
    victim.unlink()
    os.mknod(victim, stat.S_IFSOCK | 0o600)
    assert reasons(sock.verify()[0]) == ["set_member_not_regular"]
    linked = fresh(world, "hard")
    os.link(objects(linked)[0], linked.root / "alias")
    assert reasons(linked.verify()[0]) == ["set_member_hardlinked"]
    nested = fresh(world, "root-not-dir")
    path = nested.root / "plain"
    path.write_bytes(b"x")
    plain = replace(nested.synthetic, set_dir=path)
    assert reasons(run(verify_args(plain, nested.key, nested.manifest))[0]) == [
        "set_member_not_regular"
    ]


def test_t6_device_node_member_is_rejected(world):
    """T6 device-node case. Creating a device node needs privilege.

    Without it the test skips with an explicit reason and the device case is an evidence gap;
    it must stay separate from the unprivileged T6 assertions.
    """
    victim = objects(world)[0]
    victim.unlink()
    try:
        os.mknod(victim, stat.S_IFCHR | 0o600, os.makedev(1, 3))
    except PermissionError:
        pytest.skip("device nodes need privilege")
    assert reasons(world.verify()[0]) == ["set_member_not_regular"]


def trust_of(arguments):
    return parse_trust(arguments)[1]


def test_t35_entry_limit_boundaries(tmp_path):
    # Reading of the frozen text: archive entries (marker + lock + objects) <= limit, and the
    # dump is one further member. With a limit of 5: 5 entries pass, 6 are rejected.
    for count, expected in ((3, 0), (4, 1)):
        world = build_world(tmp_path / f"n{count}", objects=count)
        trust = trust_of(verify_args(world.synthetic, world.key, world.manifest))
        out = verify(trust, limits=Limits(archive_entries=5)).to_dict()
        assert (out["reasons"] == []) is (expected == 0), (count, out["reasons"])
        if expected:
            assert out["reasons"] == ["set_entry_limit_exceeded"]
    assert Limits().archive_entries == 8192 and Limits().total_members == 8193


def test_t35_limits_are_enforced_before_hashing(world, monkeypatch):
    calls = []
    monkeypatch.setattr(fsset.OpenSet, "hash_member", lambda *a, **k: calls.append(1))
    trust = trust_of(verify_args(world.synthetic, world.key, world.manifest))
    for limits, code in (
        (Limits(object_bytes=5), "set_size_limit_exceeded"),
        (Limits(archive_payload_bytes=10), "set_size_limit_exceeded"),
        (Limits(dump_bytes=5), "set_size_limit_exceeded"),
        (Limits(archive_entries=2), "set_entry_limit_exceeded"),
        (Limits(marker_bytes=5), "archive_marker_mismatch"),
    ):
        assert verify(trust, limits=limits).to_dict()["reasons"] == [code]
    assert calls == []


def test_t35_manifest_and_key_limits_and_buffer(world):
    size = world.manifest.stat().st_size
    trust = trust_of(verify_args(world.synthetic, world.key, world.manifest))
    assert verify(trust, limits=Limits(manifest_bytes=size)).to_dict()["reasons"] == []
    over = verify(trust, limits=Limits(manifest_bytes=size - 1)).to_dict()
    assert over["reasons"] == ["manifest_too_large"]
    assert verify(trust, limits=Limits(key_file_bytes=10)).to_dict()["reasons"] == [
        "key_file_unsafe"
    ]
    tiny = verify(trust, limits=Limits(buffer_bytes=3)).to_dict()  # constant-memory streaming
    assert tiny["reasons"] == [] and tiny["integrity"] == "integrity_valid"


def test_t35_dump_ceiling_is_a_labelled_unapproved_placeholder():
    from app.recovery_set import format as module

    assert module.PROVISIONAL_UNAPPROVED_DUMP_CEILING_BYTES == 64 * 1024**3
    assert Limits().dump_bytes == module.PROVISIONAL_UNAPPROVED_DUMP_CEILING_BYTES
    source = Path(module.__file__).read_text()
    assert "NOT an approved or measured operational capacity" in source


def test_limit_injection_is_unreachable_from_cli_environment_or_configuration(world, monkeypatch):
    options = {*GENERATE_OPTIONS, *VERIFY_OPTIONS, *VERIFY_FLAGS}
    assert not any("limit" in option or "fault" in option for option in options)
    package = Path(fsset.__file__).parent
    for source in package.glob("*.py"):
        text = source.read_text()
        assert "os.environ" not in text and "getenv" not in text, source.name
        assert "configparser" not in text and "tomllib" not in text, source.name
    monkeypatch.setenv("BUTLER_RECOVERY_SET_DUMP_BYTES", "1")
    assert world.verify()[1] == 0
    for flag in ("--limit", "--max-dump-bytes", "--fault"):
        output, status = run([*verify_args(world.synthetic, world.key, world.manifest), flag, "1"])
        assert status == 2 and output["reasons"] == ["trust_input_malformed"]


def test_t36_paths_overlap(world):
    base = verify_args(world.synthetic, world.key, world.manifest)
    inside = str(world.synthetic.set_dir / "manifest.json")
    for flag, value in (
        ("--manifest", inside),
        ("--recovery-key", str(world.synthetic.set_dir / "k")),
        ("--manifest", str(world.key.path)),
    ):
        args = list(base)
        args[args.index(flag) + 1] = value
        output, status = run(args)
        assert status == 2 and output["reasons"] == ["paths_overlap"]
        assert output["integrity"] == "integrity_not_evaluated"
    gen = generate_args(world.synthetic, world.key, world.synthetic.set_dir / "m")
    assert run(gen)[0]["reasons"] == ["paths_overlap"]


def add_pending(synthetic):
    name = f".pending-{uuid.uuid4().hex}-{uuid.uuid4().hex}"
    write_private(synthetic.set_dir / "archive" / name, b"partial")
    return name


def test_t49_pending_objects_refuse_verify_and_generate(world, tmp_path):
    pending = add_pending(world.synthetic)
    out = world.verify()[0]
    assert reasons(out) == ["archive_pending_objects_present"]
    assert out["integrity"] == "integrity_invalid"
    assert (world.synthetic.set_dir / "archive" / pending).exists()
    synthetic = make_set(tmp_path / "g" / "s")
    add_pending(synthetic)
    key = make_key(tmp_path / "g" / "k")
    output = private_dir(tmp_path / "g" / "o") / "manifest.json"
    result, status = run_generate(synthetic, key, output)
    assert status == 1 and result["reasons"] == ["archive_pending_objects_present"]
    assert result["publication"] == "not_published" and not output.exists()


@pytest.mark.parametrize("change", ["add", "remove", "modify", "pending"])
def test_t50_archive_changes_between_generation_passes(tmp_path, change):
    synthetic = make_set(tmp_path / "s")
    key = make_key(tmp_path / "k")
    output = private_dir(tmp_path / "o") / "manifest.json"
    archive = synthetic.set_dir / "archive"
    first_object = min(archive.glob("*.original"))

    def mutate():
        if change == "add":
            write_private(archive / f"{uuid.uuid4().hex}-v1.original", b"new")
        elif change == "remove":
            first_object.unlink()
        elif change == "modify":
            first_object.write_bytes(b"changed bytes")
        else:
            add_pending(synthetic)

    from recovery_set_support import generate_args as args_for

    from app.recovery_set.cli import parse_trust as parse

    _, trust = parse(args_for(synthetic, key, output))
    result = generate(trust, faults=InjectedFaults({"between_passes": mutate})).to_dict()
    assert result["reasons"] == ["archive_changed_during_generation"]
    assert result["publication"] == "not_published" and not output.exists()


def test_t52_mode_and_link_invariants(world):
    set_dir = world.synthetic.set_dir
    dump = set_dir / "database.dump"
    cases = [
        (dump, 0o620, "set_member_unsafe_mode"),
        (dump, 0o602, "set_member_unsafe_mode"),
        (dump, 0o640, "set_member_unsafe_mode"),
        (dump, 0o604, "set_member_unsafe_mode"),
        (set_dir, 0o750, "set_member_unsafe_mode"),
        (set_dir, 0o705, "set_member_unsafe_mode"),
        (set_dir, 0o720, "set_member_unsafe_mode"),
        (set_dir / "archive", 0o750, "set_member_unsafe_mode"),
        (set_dir / "archive", 0o702, "set_member_unsafe_mode"),
        (set_dir, 0o702, "set_member_unsafe_mode"),  # remaining group/other read/write combinations
        (set_dir / "archive", 0o720, "set_member_unsafe_mode"),
        (set_dir / "archive", 0o705, "set_member_unsafe_mode"),
        (world.manifest, 0o640, "manifest_file_unsafe"),
        (world.manifest, 0o604, "manifest_file_unsafe"),
        (world.manifest, 0o620, "manifest_file_unsafe"),
        (world.manifest, 0o602, "manifest_file_unsafe"),
    ]
    for path, mode, expected in cases:
        original = stat.S_IMODE(path.stat().st_mode)
        path.chmod(mode)
        out = world.verify()[0]
        path.chmod(original)
        assert expected in reasons(out), (path.name, oct(mode))
        assert out["notes"] == [], "no permission note exists"
    for text in ("confiden", "protect", "secure"):
        assert text not in str(world.verify()[0]).lower()
    # execute (search) bits are not evaluated and owner-only modes pass
    set_dir.chmod(0o711)
    assert world.verify()[1] == 0
    set_dir.chmod(0o700)
    # a read-only owner copy still verifies: the verifier never needs write access to the set
    dump.chmod(0o400)
    assert world.verify()[1] == 0


def test_set_is_never_modified_by_verify(world):
    def snapshot():
        return sorted(
            (str(p), p.stat().st_mtime_ns, p.stat().st_size, stat.S_IMODE(p.stat().st_mode))
            for p in world.synthetic.set_dir.rglob("*")
        )

    before = snapshot()
    assert world.verify()[1] == 0
    assert snapshot() == before


def test_enumeration_order_is_independent_of_filesystem_order(tmp_path):
    first = make_set(tmp_path / "a" / "s", objects=5)
    second = make_set(tmp_path / "b" / "s", objects=0)
    for name in reversed(first.objects):
        write_private(
            second.set_dir / "archive" / name, (first.set_dir / "archive" / name).read_bytes()
        )
    for name in ("database.dump",):
        write_private(second.set_dir / name, (first.set_dir / name).read_bytes())
    marker = (first.set_dir / "archive" / ".archive.json").read_bytes()
    write_private(second.set_dir / "archive" / ".archive.json", marker)
    from recovery_set_support import generate_args as args_for

    from app.recovery_set.cli import parse_trust as parse

    key = make_key(tmp_path / "k")
    manifests = []
    for number, synthetic in enumerate((first, second)):
        output = private_dir(tmp_path / f"o{number}") / "m"
        _, trust = parse(
            args_for(SyntheticSet(synthetic.root, synthetic.set_dir, "", [], True), key, output)
        )
        fixed = {"set_id": "22222222-2222-4222-8222-222222222222"}
        fixed["created_at"] = "2026-11-14T00:00:00Z"
        assert generate(trust, **fixed).to_dict()["reasons"] == []
        manifests.append(output.read_bytes())
    assert manifests[0] == manifests[1]


def test_no_database_or_network_modules_are_loaded_by_the_tool():
    code = (
        "import sys, app.recovery_set.cli;"
        "assert 'app.db' not in sys.modules and 'app.config' not in sys.modules;"
        "assert 'httpx' not in sys.modules and 'psycopg' not in sys.modules"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-c", code],
        check=False,
        capture_output=True,
        cwd=Path(fsset.__file__).parents[2],
    )
    assert done.returncode == 0, done.stderr[-300:]


# --- A10: explicit fail-on-attempt guards -------------------------------------------------------
# Frozen A10: the verifier uses no database, no network and never writes inside SET. The import and
# snapshot tests above show the absence of modules and unchanged bytes; they would not notice an
# attempt that is caught, retried or undone. These guards record every attempt at the Python-level
# entry points below while verify runs, and the tests assert the record is empty.
#
# What is intercepted: socket creation and name resolution (socket.socket, create_connection,
# getaddrinfo, gethostbyname*, socketpair, fromfd, create_server); process creation
# (subprocess.Popen, os.system, os.fork, os.posix_spawn*, os.exec*); database entry points
# (psycopg.connect and Connection.connect, sqlalchemy.create_engine, Engine.connect/begin and
# DefaultDialect.connect); every write-capable os.open (O_WRONLY, O_RDWR, O_CREAT, O_TRUNC,
# O_APPEND, O_EXCL, O_TMPFILE) with or without dir_fd (the descriptor-relative interface the
# verifier actually uses); write-mode builtins.open and io.open (and so Path.open/write_text);
# os.write (except fds 1 and 2) and the other descriptor writers; and namespace or metadata
# mutation (unlink, remove, rmdir, rename, replace, link, symlink, mkdir, mkfifo, mknod, chmod,
# fchmod, chown, fchown, lchown, utime, setxattr, removexattr).
#
# Limits: Python-level attribute interception only. It cannot see references bound before it was
# installed, C extensions, ctypes or raw system calls, or other process APIs; it checks the write
# intent of an open, not its path, so it is stricter than "inside SET" (any write-capable open
# anywhere is a violation). It proves that this implementation, exercised on the cases below, makes
# no such attempt; it is not a sandbox.

WRITE_OPEN_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND | os.O_EXCL
O_TMPFILE = getattr(os, "O_TMPFILE", 0)  # on Linux this includes the O_DIRECTORY bit


def is_write_open(flags):
    """True for any write-capable open; O_TMPFILE only counts when all of its bits are set."""
    return bool(flags & WRITE_OPEN_FLAGS) or (O_TMPFILE != 0 and flags & O_TMPFILE == O_TMPFILE)


class ProhibitedAttempt(Exception):
    pass


class Guards:
    def __init__(self):
        self.attempts = []  # (kind, detail) of every prohibited call
        self.read_opens = []  # (used dir_fd, flags) of every permitted read-only os.open

    def trip(self, kind, detail=""):
        self.attempts.append((kind, str(detail)[:80]))
        raise ProhibitedAttempt(kind)

    def _always(self, kind):
        def guard(*args, **kwargs):
            self.trip(kind, args[:1])

        return guard


@contextmanager
def prohibited_effects():
    """Install the A10 guards for the duration of the block and yield the ``Guards`` record."""
    import psycopg
    import sqlalchemy
    import sqlalchemy.engine.default

    guards = Guards()
    real_open, real_builtin_open, real_write = os.open, builtins.open, os.write

    def guarded_os_open(path, flags, mode=0o777, *, dir_fd=None):
        if is_write_open(flags):
            guards.trip("os.open write-capable", (path, hex(flags)))
        guards.read_opens.append((dir_fd is not None, flags))
        return real_open(path, flags, mode, dir_fd=dir_fd)

    def guarded_open(file, mode="r", *args, **kwargs):
        if set(str(kwargs.get("mode", mode))) & set("wax+"):
            guards.trip("open write mode", file)
        return real_builtin_open(file, mode, *args, **kwargs)

    def guarded_write(descriptor, data):
        if descriptor not in (1, 2):
            guards.trip("os.write", descriptor)
        return real_write(descriptor, data)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, "open", guarded_os_open)
        patch.setattr(os, "write", guarded_write)
        patch.setattr(builtins, "open", guarded_open)
        patch.setattr(io, "open", guarded_open)
        for name in (
            "pwrite", "writev", "pwritev", "ftruncate", "truncate", "sendfile", "copy_file_range",
            "unlink", "remove", "rmdir", "rename", "replace", "link", "symlink", "mkdir", "mkfifo",
            "mknod", "chmod", "fchmod", "chown", "fchown", "lchown", "utime", "setxattr",
            "removexattr", "system", "fork", "posix_spawn", "posix_spawnp", "execv", "execve",
        ):  # fmt: skip
            if hasattr(os, name):
                patch.setattr(os, name, guards._always(f"os.{name}"))
        for name in (
            "socket", "create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex",
            "socketpair", "fromfd", "create_server",
        ):  # fmt: skip
            patch.setattr(socket, name, guards._always(f"socket.{name}"))
        patch.setattr(subprocess, "Popen", guards._always("subprocess.Popen"))
        patch.setattr(psycopg, "connect", guards._always("psycopg.connect"))
        patch.setattr(
            psycopg.Connection, "connect", staticmethod(guards._always("psycopg.connect"))
        )
        patch.setattr(sqlalchemy, "create_engine", guards._always("sqlalchemy.create_engine"))
        patch.setattr(
            sqlalchemy.engine, "create_engine", guards._always("sqlalchemy.create_engine")
        )
        patch.setattr(sqlalchemy.engine.Engine, "connect", guards._always("Engine.connect"))
        patch.setattr(sqlalchemy.engine.Engine, "begin", guards._always("Engine.begin"))
        patch.setattr(
            sqlalchemy.engine.default.DefaultDialect, "connect", guards._always("dialect.connect")
        )
        yield guards


def test_a10_guards_intercept_each_prohibited_entry_point(tmp_path):
    """Positive controls: a guard that never fires would make the A10 tests below vacuous."""
    import psycopg
    import sqlalchemy

    engine = sqlalchemy.create_engine("sqlite://")  # created before the guards: Engine.connect only
    target = tmp_path / "file"
    target.write_bytes(b"x")
    read_end, write_end = os.pipe()
    directory_fd = os.open(tmp_path, os.O_RDONLY)  # held explicitly; closed in the finally below
    probes = {
        "socket.socket": lambda: socket.socket(),
        "socket.create_connection": lambda: socket.create_connection(("127.0.0.1", 9)),
        "socket.getaddrinfo": lambda: socket.getaddrinfo("example.invalid", 80),
        "psycopg.connect": lambda: psycopg.connect("dbname=none"),
        "sqlalchemy.create_engine": lambda: sqlalchemy.create_engine("sqlite://"),
        "Engine.connect": lambda: engine.connect(),
        "os.open O_WRONLY": lambda: os.open(target, os.O_WRONLY),
        "os.open O_RDONLY|O_CREAT": lambda: os.open(target, os.O_RDONLY | os.O_CREAT),
        "os.open O_TMPFILE": lambda: os.open(tmp_path, O_TMPFILE | os.O_WRONLY),
        "os.open O_TRUNC dir_fd": lambda: os.open(
            target.name, os.O_RDWR | os.O_TRUNC, dir_fd=directory_fd
        ),
        "open w": lambda: open(target, "w"),  # noqa: SIM115
        "open ab keyword": lambda: open(target, mode="ab"),  # noqa: SIM115
        "io.open r+": lambda: io.open(target, "r+"),  # noqa: SIM115, UP020
        "Path.write_text": lambda: target.write_text("y"),
        "os.write": lambda: os.write(write_end, b"x"),
        "os.ftruncate": lambda: os.ftruncate(write_end, 0),
        "os.unlink": lambda: os.unlink(target),
        "os.rename": lambda: os.rename(target, tmp_path / "other"),
        "os.mkdir": lambda: os.mkdir(tmp_path / "dir"),
        "os.chmod": lambda: os.chmod(target, 0o600),
        "os.utime": lambda: os.utime(target),
        "subprocess.Popen": lambda: subprocess.Popen(["true"]),
        "os.system": lambda: os.system("true"),
    }
    try:
        with prohibited_effects() as guards:
            for name, probe in probes.items():
                before = len(guards.attempts)
                with pytest.raises(ProhibitedAttempt):
                    probe()
                assert len(guards.attempts) == before + 1, name
            # permitted: read-only opens, including descriptor-relative ones
            directory = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
            descriptor = os.open(target.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(descriptor)
            os.close(directory)
            with open(target, "rb") as handle:
                assert handle.read() == b"x"
            assert os.write(2, b"") == 0  # fds 1 and 2 stay usable for the test runner
        assert len(guards.attempts) == len(probes)
        assert (True, os.O_RDONLY | os.O_NOFOLLOW) in guards.read_opens
    finally:
        os.close(directory_fd)
        os.close(read_end)
        os.close(write_end)
        engine.dispose()
    assert target.read_bytes() == b"x"  # nothing the probes attempted took effect


def make_read_only(world):
    """Owner-read-only set: members 0400, SET and archive/ 0500. Returns a restore callback."""
    set_dir = world.synthetic.set_dir
    paths = [p for p in set_dir.rglob("*") if p.is_file()]
    directories = [set_dir / "archive", set_dir]
    original = {p: stat.S_IMODE(p.stat().st_mode) for p in paths + directories}
    for path in paths:
        path.chmod(0o400)
    for directory in directories:
        directory.chmod(0o500)

    def restore():
        for directory in reversed(directories):
            directory.chmod(original[directory])
        for path in paths:
            path.chmod(original[path])

    return restore


def tamper(world, case):
    set_dir = world.synthetic.set_dir
    if case == "hash_mismatch":
        dump = set_dir / "database.dump"
        data = bytearray(dump.read_bytes())
        data[0] ^= 1
        dump.write_bytes(bytes(data))
    elif case == "missing_member":
        objects(world)[0].unlink()
    elif case == "unexpected_member":
        write_private(set_dir / "notes.txt", b"x")


@pytest.mark.parametrize(
    "case,status,expected",
    [
        ("valid", 0, []),
        ("hash_mismatch", 1, ["set_member_hash_mismatch"]),
        ("missing_member", 1, ["set_member_missing"]),
        ("unexpected_member", 1, ["set_member_unexpected"]),
    ],
)
def test_a10_verify_attempts_no_database_network_or_write_on_a_read_only_set(
    world, case, status, expected
):
    tamper(world, case)  # fixtures are assembled before the guards are installed
    restore = make_read_only(world)
    try:
        if os.geteuid() != 0:  # unprivileged: the kernel itself refuses writes to the set
            with pytest.raises(PermissionError):
                open(world.synthetic.set_dir / "database.dump", "ab")  # noqa: SIM115
        with prohibited_effects() as guards:
            output, code = world.verify()
        assert guards.attempts == [], guards.attempts
        # the guards were on the real path: the verifier opened set members through them,
        # including descriptor-relative opens (dir_fd), and only ever read-only
        assert any(used_dir_fd for used_dir_fd, _ in guards.read_opens)
        assert len(guards.read_opens) >= 4
        assert all(not is_write_open(flags) for _, flags in guards.read_opens)
        assert (code, reasons(output)) == (status, expected)
        if case == "valid":
            assert output["integrity"] == "integrity_valid"
            assert output["authenticity"] == "authenticity_valid"
    finally:
        restore()


def test_modification_during_a_read_with_unchanged_size_is_detected(world, monkeypatch):
    """The post-read fstat catches a same-size change (mtime) that the byte count cannot."""
    target = world.synthetic.set_dir / "database.dump"
    real_read, state = os.read, {"done": False}

    def read(descriptor, count):
        if not state["done"] and os.fstat(descriptor).st_ino == target.stat().st_ino:
            state["done"] = True
            stamp = target.stat().st_mtime_ns + 5_000_000_000
            os.utime(target, ns=(stamp, stamp))
        return real_read(descriptor, count)

    monkeypatch.setattr(os, "read", read)
    output = world.verify()[0]
    assert output["reasons"] == ["set_changed_during_read"]
    assert output["integrity"] == "integrity_invalid"


def test_t7_case_variant_names_on_disk_are_ambiguous(world):
    """T7 "case-variant duplicate": two names that differ only in case are never guessed between."""
    root_variant = fresh(world, "case-root")
    write_private(root_variant.synthetic.set_dir / "Database.dump", b"x")
    assert reasons(root_variant.verify()[0]) == ["set_enumeration_ambiguous"]
    archive_variant = fresh(world, "case-archive")
    first = objects(archive_variant)[0]
    write_private(first.with_name(first.name.upper()), b"x")
    assert reasons(archive_variant.verify()[0]) == ["set_enumeration_ambiguous"]
