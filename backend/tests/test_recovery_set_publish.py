"""Spec 074 B040 to B042: atomic publication, durability, notes, unsupported filesystems
(T27 to T31, T37 to T43, T51). Real subprocesses with SIGKILL at controlled points and fault
injection through the test-only function parameter; synthetic data only."""

import errno
import json
import os
import signal
import stat
import subprocess
import sys
import threading
import uuid
from pathlib import Path

import pytest
from recovery_set_support import (
    generate_args,
    make_key,
    make_set,
    private_dir,
    run_verify,
    verify_args,
    write_private,
)

from app.recovery_set import fsset
from app.recovery_set.cli import parse_trust, run
from app.recovery_set.format import parse_manifest
from app.recovery_set.generate import generate
from app.recovery_set.publish import TEMP_PREFIX, InjectedFaults

BACKEND = Path(fsset.__file__).parents[2]
FIXED = {"set_id": "33333333-3333-4333-8333-333333333333", "created_at": "2026-11-14T00:00:00Z"}


class Case:
    def __init__(self, tmp_path, archive=True):
        self.root = private_dir(tmp_path / f"c{uuid.uuid4().hex[:6]}")
        self.synthetic = make_set(self.root / "s", archive=archive)
        self.key = make_key(self.root / "k")
        self.out_dir = private_dir(self.root / "o")
        self.output = self.out_dir / "manifest.json"

    def args(self, output=None):
        return generate_args(self.synthetic, self.key, output or self.output)

    def run(self, faults=None, output=None, **kwargs):
        _, trust = parse_trust(self.args(output))
        return generate(trust, faults=faults, **kwargs)

    def generate(self, faults=None, output=None, **kwargs):
        return self.run(faults, output, **kwargs).to_dict()

    def temporaries(self):
        return sorted(p.name for p in self.out_dir.iterdir() if p.name.startswith(TEMP_PREFIX))

    def verify(self):
        return run_verify(self.synthetic, self.key, self.output)


def raising(error):
    def callback():
        raise error

    return callback


def faults(**points):
    return InjectedFaults(points)


CHILD = """
import json, os, signal, sys
from app.recovery_set.cli import parse_trust
from app.recovery_set.generate import generate
from app.recovery_set.publish import InjectedFaults
point, args = sys.argv[1], json.loads(sys.argv[2])
_, trust = parse_trust(args)
kill = lambda: os.kill(os.getpid(), signal.SIGKILL)
generate(trust, faults=InjectedFaults({point: kill}))
"""


def killed_at(case, point):
    done = subprocess.run(
        [sys.executable, "-I", "-c", CHILD, point, json.dumps(case.args())],
        check=False,
        capture_output=True,
        cwd=BACKEND,
    )
    assert done.returncode == -signal.SIGKILL, done.stderr[-200:]


@pytest.mark.parametrize("point", ["mid_write", "after_flush"])
def test_t27_kill_before_publication_leaves_no_final_manifest(tmp_path, point):
    case = Case(tmp_path)
    killed_at(case, point)
    assert not case.output.exists()  # never a prefix
    assert len(case.temporaries()) == 1  # a recoverable artifact, never deleted by the tool
    again = case.generate()
    assert again["reasons"] == [] and again["publication"] == "published_durable"
    assert again["notes"] == ["stale_temporary_present"]  # reported, not a failure reason
    assert len(case.temporaries()) == 1  # a later run never deletes it
    assert case.verify()[1] == 0


@pytest.mark.parametrize("point", ["after_link", "after_publish", "before_dir_fsync"])
def test_t27_kill_after_publication_before_the_directory_flush(tmp_path, point):
    """T27 third point: SIGKILL after publication, before the directory flush.

    The final path holds the complete valid manifest and a retry is refused with ``output_exists``
    without touching it. A temporary left behind is preserved and reported by the note: at
    ``after_link`` the tool has not yet removed its own temporary, so it survives as a second hard
    link to the final bytes; at ``after_publish`` and ``before_dir_fsync`` the tool has already
    removed it, so there is nothing to preserve and no note. Every preservation check below runs
    before the deliberate cleanup that lets the final manifest verify again.
    """
    case = Case(tmp_path)
    killed_at(case, point)
    final = case.output
    final_bytes = final.read_bytes()
    parse_manifest(final_bytes)  # a complete valid manifest, never a prefix
    published = final.stat()
    leftovers = case.temporaries()
    if point == "after_link":
        assert len(leftovers) == 1
        temporary = case.out_dir / leftovers[0]
        info = temporary.stat()
        assert temporary.read_bytes() == final_bytes  # complete: never mistaken for a prefix
        assert (info.st_ino, info.st_dev) == (published.st_ino, published.st_dev)
        assert info.st_nlink == published.st_nlink == 2
        assert info.st_mode & 0o777 == 0o600
    else:
        assert leftovers == [] and published.st_nlink == 1

    retry = case.generate()
    assert retry["reasons"] == ["output_exists"] and retry["publication"] == "not_published"
    assert retry["notes"] == (["stale_temporary_present"] if leftovers else [])
    assert final.read_bytes() == final_bytes  # the retry never changed the final manifest
    assert (final.stat().st_ino, final.stat().st_nlink) == (published.st_ino, published.st_nlink)
    assert case.temporaries() == leftovers  # and never deleted the leftover temporary
    if leftovers:
        assert (case.out_dir / leftovers[0]).read_bytes() == final_bytes

    if point == "after_link":
        # the leftover temporary is a hard link to the same bytes: the final manifest then has
        # two links and fails the mandatory single-link rule until the operator removes it.
        failed, status = case.verify()
        assert failed["reasons"] == ["manifest_file_unsafe"] and status == 1
        assert failed["notes"] == []  # verify performs no stale-temporary scan
        assert case.temporaries() == leftovers  # verification deletes nothing either
        (case.out_dir / leftovers[0]).unlink()  # deliberate test cleanup, only now
    assert case.verify()[1] == 0
    assert final.read_bytes() == final_bytes


def test_t28_existing_destination_is_never_modified(tmp_path):
    case = Case(tmp_path)
    case.output.write_bytes(b"existing bytes")
    case.output.chmod(0o600)
    result = case.generate()
    assert result["reasons"] == ["output_exists"] and result["publication"] == "not_published"
    assert case.output.read_bytes() == b"existing bytes" and case.temporaries() == []


def test_t29_concurrent_generation_to_one_output(tmp_path):
    case = Case(tmp_path)
    processes = [
        subprocess.Popen(
            [sys.executable, "-I", "-m", "app.recovery_set", *case.args()],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=BACKEND,
        )
        for _ in range(6)
    ]
    outputs = [(p.communicate()[0], p.returncode) for p in processes]
    codes = sorted(status for _, status in outputs)
    assert codes == [0, 1, 1, 1, 1, 1]
    for data, status in outputs:
        if status:
            assert json.loads(data)["reasons"] == ["output_exists"]
    assert case.temporaries() == [] and case.verify()[1] == 0


def test_t30_concurrent_generation_to_different_outputs(tmp_path):
    case = Case(tmp_path)
    results, targets = [], [case.out_dir / f"m{n}" for n in range(6)]

    def work(target):
        results.append(case.generate(output=target, **FIXED))

    threads = [threading.Thread(target=work, args=(t,)) for t in targets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert all(r["reasons"] == [] and r["publication"] == "published_durable" for r in results)
    assert len({t.read_bytes() for t in targets}) == 1  # identical inputs, identical manifests


def test_t31_filesystem_errors_leave_no_final_manifest(tmp_path):
    cases = {
        "before_temp_create": errno.EROFS,
        "mid_write": errno.ENOSPC,
        "before_flush": errno.EIO,
    }
    for point, number in cases.items():
        case = Case(tmp_path)
        result = case.generate(faults(**{point: raising(OSError(number, "x"))}))
        assert result["reasons"] == ["io_error"] and result["publication"] == "not_published"
        assert not case.output.exists() and case.temporaries() == []
    case = Case(tmp_path)
    original = fsset.OpenSet.hash_member
    state = {"done": False}

    def shrink(self, found, keep=False):
        if not state["done"]:
            state["done"] = True
            (case.synthetic.set_dir / "database.dump").write_bytes(b"truncated")
        return original(self, found, keep)

    fsset.OpenSet.hash_member = shrink
    try:
        result = case.generate()
    finally:
        fsset.OpenSet.hash_member = original
    assert result["reasons"] == ["set_changed_during_read"] and not case.output.exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
def test_t31_read_only_output_directory(tmp_path):  # pragma: no cover - needs a non-root user
    case = Case(tmp_path)
    case.out_dir.chmod(0o500)
    try:
        assert case.generate()["reasons"] == ["io_error"]
    finally:
        case.out_dir.chmod(0o700)


@pytest.mark.parametrize(
    ("point", "action"),
    [
        ("before_temp_create", raising(OSError(errno.EIO, "x"))),
        ("mid_write", raising(OSError(errno.ENOSPC, "x"))),
        ("before_flush", raising(OSError(errno.EIO, "x"))),
        ("before_publish", raising(OSError(errno.EIO, "x"))),
    ],
)
def test_t37_failure_before_publication(tmp_path, point, action):
    case = Case(tmp_path)
    outcome = case.run(faults(**{point: action}))
    result = outcome.to_dict()
    assert result["publication"] == "not_published" and result["reasons"] in (
        ["io_error"],
        ["filesystem_unsupported"],
    )
    assert not case.output.exists() and case.temporaries() == []
    assert outcome.exit_status() == 1


def test_t37_validation_failure_publishes_nothing(tmp_path):
    case = Case(tmp_path)
    write_private(case.synthetic.set_dir / "extra", b"x")
    result = case.generate()
    assert result["reasons"] == ["set_member_unexpected"]
    assert result["publication"] == "not_published" and not case.output.exists()
    assert case.temporaries() == []


DIRECTORY_FAULTS = [
    OSError(errno.EIO, "x"),
    OSError(errno.EBADF, "x"),
    InterruptedError(errno.EINTR, "x"),  # persistent EINTR
    RuntimeError("flush result cannot be determined"),
]


@pytest.mark.parametrize("error", DIRECTORY_FAULTS)
def test_t38_t39_directory_flush_failure_is_never_durable_success(tmp_path, error):
    case = Case(tmp_path)
    result = case.generate(faults(before_dir_fsync=raising(error)))
    text = json.dumps(result)
    assert result["reasons"] == ["publication_durability_uncertain"]
    assert result["publication"] == "published_durability_uncertain"
    assert "published_durable" not in text.replace("published_durability_uncertain", "")
    assert "not_published" not in text
    parse_manifest(case.output.read_bytes())  # complete and valid, never deleted or renamed
    assert case.temporaries() == []
    # exit status through the real command path is 1, never 0
    _, trust = parse_trust(case.args(case.out_dir / "again"))
    from app.recovery_set.generate import generate as gen

    again = gen(trust, faults=faults(before_dir_fsync=raising(error)))
    assert again.exit_status() == 1


def test_t38_exit_status_is_one_for_uncertain_publication(tmp_path):
    case = Case(tmp_path)
    _, trust = parse_trust(case.args())
    result = generate(trust, faults=faults(before_dir_fsync=raising(OSError(errno.EIO, "x"))))
    assert result.exit_status() == 1 and result.publication == "published_durability_uncertain"


def test_t40_retry_against_an_existing_final_manifest(tmp_path):
    case = Case(tmp_path)
    case.generate(faults(before_dir_fsync=raising(OSError(errno.EIO, "x"))))
    before = case.output.read_bytes()
    retry = case.generate()
    assert retry["reasons"] == ["output_exists"] and retry["publication"] == "not_published"
    assert case.output.read_bytes() == before and case.temporaries() == []
    plain = Case(tmp_path)
    plain.output.write_bytes(b"plain")
    assert plain.generate()["reasons"] == ["output_exists"] and plain.temporaries() == []


def test_t41_inspection_and_recovery_of_an_uncertain_manifest(tmp_path):
    case = Case(tmp_path)
    case.generate(faults(before_dir_fsync=raising(OSError(errno.EIO, "x"))))
    output, status = case.verify()
    assert status == 0 and output["reasons"] == []  # no marker of the uncertainty
    case.output.rename(case.out_dir / "moved-aside")  # the operator's action, outside the tool
    result = case.generate()
    assert result["publication"] == "published_durable" and result["reasons"] == []
    assert case.verify()[1] == 0


def test_t42_note_on_a_successful_run(tmp_path):
    case = Case(tmp_path)
    write_private(case.out_dir / f"{TEMP_PREFIX}abandoned", b"partial")
    result = case.generate()
    assert result["publication"] == "published_durable" and result["reasons"] == []
    assert result["notes"] == ["stale_temporary_present"]
    assert (result["integrity"], result["authenticity"], result["freshness"]) == (
        "integrity_valid",
        "authenticity_valid",
        "freshness_not_evaluated",
    )


def test_t43_notes_are_bounded_and_non_leaking(tmp_path):
    names = [
        f"{TEMP_PREFIX}one",
        f"{TEMP_PREFIX}\x07\x1b[31mcontrol",
        f"{TEMP_PREFIX}" + "x" * 150,
        f"{TEMP_PREFIX}" + "ab" * 32,  # key-like
    ]
    for count in (0, 1, 4):
        case = Case(tmp_path)
        for name in names[:count]:
            write_private(case.out_dir / name, b"x")
        result = case.generate()
        assert result["notes"] == (["stale_temporary_present"] if count else [])
        text = json.dumps(result)
        assert "control" not in text and "xxx" not in text and str(case.out_dir) not in text
        assert len(result["notes"]) <= 1 and result["notes"] == sorted(set(result["notes"]))
    failing = Case(tmp_path)
    write_private(failing.out_dir / names[0], b"x")
    write_private(failing.synthetic.set_dir / "extra", b"x")
    result = failing.generate()
    assert result["notes"] == ["stale_temporary_present"]  # beside the failure, not instead
    assert result["reasons"] == ["set_member_unexpected"]
    verify_case = Case(tmp_path)
    verify_case.generate()
    write_private(verify_case.out_dir / names[0], b"x")
    assert verify_case.verify()[0]["notes"] == []  # verify never scans for temporaries
    inside = Case(tmp_path)
    inside.generate()
    write_private(inside.synthetic.set_dir / names[0], b"x")
    output = inside.verify()[0]
    assert output["reasons"] == ["set_member_unexpected"] and output["notes"] == []


def test_t43_only_the_first_sixty_four_sorted_entries_are_examined(tmp_path):
    case = Case(tmp_path)
    for number in range(70):
        write_private(case.out_dir / f"!filler-{number:03d}", b"x")
    write_private(case.out_dir / f"{TEMP_PREFIX}late", b"x")
    assert case.generate()["notes"] == []  # documented bound: no detection past 64 entries


@pytest.mark.parametrize("number", [errno.EPERM, errno.ENOTSUP, errno.EXDEV, errno.EINVAL])
def test_t51_unsupported_filesystem_never_falls_back(tmp_path, monkeypatch, number):
    case = Case(tmp_path)

    def forbidden(*args, **kwargs):  # a replacing rename, copy or check-then-write is never used
        raise AssertionError("forbidden fallback primitive")

    for name in ("rename", "replace", "renames"):
        monkeypatch.setattr(os, name, forbidden)
    result = case.generate(faults(before_publish=raising(OSError(number, "x"))))
    assert result["reasons"] == ["filesystem_unsupported"]
    assert result["publication"] == "not_published"
    assert not case.output.exists() and case.temporaries() == []


def test_t51_successful_publication_never_uses_a_replacing_rename(tmp_path, monkeypatch):
    case = Case(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("forbidden fallback primitive")

    for name in ("rename", "replace", "renames"):
        monkeypatch.setattr(os, name, forbidden)
    assert case.generate()["publication"] == "published_durable"


def test_t51_unsupported_directory_flush_is_reported_as_uncertain(tmp_path):
    case = Case(tmp_path)
    result = case.generate(faults(before_dir_fsync=raising(OSError(errno.EINVAL, "x"))))
    assert result["publication"] == "published_durability_uncertain"
    assert result["reasons"] == ["publication_durability_uncertain"]


def test_output_path_safety(tmp_path):
    case = Case(tmp_path)
    link = case.out_dir / "link"
    link.symlink_to(case.out_dir / "target")
    assert case.generate(output=link)["reasons"] == ["output_unsafe"]
    directory = private_dir(case.out_dir / "adir")
    assert case.generate(output=directory)["reasons"] == ["output_unsafe"]
    loose = private_dir(case.root / "loose", 0o770)
    assert case.generate(output=loose / "m")["reasons"] == ["output_unsafe"]
    for result in (case.generate(output=link), case.generate(output=loose / "m")):
        assert result["publication"] == "not_published"


def test_generate_refuses_a_mismatched_key_or_unknown_schema_head(tmp_path):
    case = Case(tmp_path)
    other_installation = str(uuid.uuid4())
    args = generate_args(case.synthetic, case.key, case.output, installation=other_installation)
    result = run(args)[0]
    assert result["reasons"] == ["key_installation_mismatch"]
    assert result["authenticity"] == "authenticity_invalid" and not case.output.exists()
    args = generate_args(case.synthetic, case.key, case.output, head="9999_unknown_future")
    result = run(args)[0]
    assert result["reasons"] == ["schema_unknown_to_verifier"]
    assert result["expectations"] == "expectations_not_met" and not case.output.exists()
    wrong = generate_args(case.synthetic, case.key, case.output, expect="absent")
    result = run(wrong)[0]
    assert result["reasons"] == ["archive_expectation_mismatch"]
    assert result["publication"] == "not_published"
    assert run(generate_args(case.synthetic, case.key, case.output))[1] == 0


def test_generated_manifest_is_owner_only_and_declares_the_operator_inputs(tmp_path):
    case = Case(tmp_path)
    digest = "ab" * 32
    extra = [
        "--model-tag", "local/model:1.0", "--model-digest", digest,
        "--work-suppression-manifest-sha256", "cd" * 32,
    ]  # fmt: skip
    result = run(generate_args(case.synthetic, case.key, case.output, extra=extra))
    assert result[1] == 0
    assert case.output.stat().st_mode & 0o777 == 0o600 and case.output.stat().st_nlink == 1
    body = json.loads(case.output.read_bytes())["payload"]["body"]
    assert body["model"] == {"declared": True, "tag": "local/model:1.0", "digest": digest}
    assert body["work_references"]["suppression_manifest_sha256"] == "cd" * 32
    assert body["work_references"]["source_checkpoint_sha256"] is None
    assert body["archive"]["object_count"] == 3 and body["archive"]["present"] is True
    assert (
        result[0]["manifest_hash"]
        and run(verify_args(case.synthetic, case.key, case.output))[1] == 0
    )


def test_generate_with_no_archive_declares_absence(tmp_path):
    case = Case(tmp_path, archive=False)
    assert case.generate()["reasons"] == []
    body = json.loads(case.output.read_bytes())["payload"]["body"]
    assert body["archive"] == {"present": False}
    assert [m["kind"] for m in body["members"]] == ["dump"]


def test_t43_note_vocabulary_is_closed():
    from app.recovery_set.result import NOTE_VOCABULARY, Result

    assert NOTE_VOCABULARY == ("stale_temporary_present",)
    bad = Result("generate")
    bad.notes = ["set_mode_group_or_other_readable"]
    with pytest.raises(ValueError):
        bad.to_dict()


def test_the_containing_directory_is_flushed_after_publication(tmp_path, monkeypatch):
    case = Case(tmp_path)
    flushed, real = [], os.fsync

    def fsync(descriptor):
        flushed.append(stat.S_ISDIR(os.fstat(descriptor).st_mode))
        return real(descriptor)

    monkeypatch.setattr(os, "fsync", fsync)
    assert case.generate()["publication"] == "published_durable"
    assert flushed == [False, True]  # the temporary file first, then the directory


def test_t31_member_removed_during_the_run_publishes_nothing(tmp_path):
    case = Case(tmp_path)
    original = fsset.OpenSet.hash_member
    state = {"done": False}

    def remove(self, found, keep=False):
        if not state["done"]:
            state["done"] = True
            (case.synthetic.set_dir / "database.dump").unlink()
        return original(self, found, keep)

    fsset.OpenSet.hash_member = remove
    try:
        result = case.generate()
    finally:
        fsset.OpenSet.hash_member = original
    assert result["reasons"] in (["set_changed_during_read"], ["io_error"])
    assert result["publication"] == "not_published" and not case.output.exists()
    assert case.temporaries() == []


@pytest.mark.parametrize("error", DIRECTORY_FAULTS)
def test_t38_printed_hash_and_published_bytes_match_the_temporary(tmp_path, error):
    """T38: the final manifest is byte-identical to the temporary and its printed hash is its own."""
    from app.recovery_set.format import manifest_hash

    case = Case(tmp_path)
    captured = {}

    def capture():  # after the link: the temporary and the final path are the same inode
        (name,) = case.temporaries()
        captured["bytes"] = (case.out_dir / name).read_bytes()

    result = case.generate(faults(after_link=capture, before_dir_fsync=raising(error)))
    assert result["publication"] == "published_durability_uncertain"
    published = case.output.read_bytes()
    assert published == captured["bytes"]  # the run did not alter the published content
    payload = json.loads(published)["payload"]
    assert result["manifest_hash"] == manifest_hash(payload)
    assert case.verify()[0]["manifest_hash"] == result["manifest_hash"]
