# ruff: noqa: F811
"""Spec 074 Phase B corrections after independent source review (synthetic data only).

Finding 1: every security-sensitive path (SET, key, manifest, output directory) is opened
component by component with O_NOFOLLOW and pinned; a link in any position is refused and a
component swapped after the open cannot redirect the operation.
Finding 2: a temporary that cannot be removed is observable and reported with the specified
``stale_temporary_present`` note; the final manifest is never touched.
"""

import errno
import os
import stat
import uuid
from pathlib import Path

import pytest
from recovery_set_support import (  # noqa: F401
    build_world,
    generate_args,
    make_key,
    private_dir,
    verify_args,
    world,
    write_private,
)

from app.recovery_set import fsset, publish
from app.recovery_set.cli import parse_trust, run
from app.recovery_set.format import CodedError, Limits
from app.recovery_set.fsset import (
    UnsafePath,
    open_directory_nofollow,
    open_set,
    read_protected_file,
)
from app.recovery_set.generate import generate
from app.recovery_set.publish import TEMP_PREFIX, InjectedFaults, publish_manifest

LIMITS = Limits()


def open_descriptors():
    return len(os.listdir("/proc/self/fd"))


def swap(args, flag, value):
    args = list(args)
    args[args.index(flag) + 1] = str(value)
    return args


def link_to(target, link):
    link.symlink_to(target, target_is_directory=True)
    return link


def replace_with_symlink(directory, attacker):
    """Rename ``directory`` away and put a symlink to ``attacker`` at its old name."""
    moved = directory.with_name(directory.name + "-moved")
    directory.rename(moved)
    directory.symlink_to(attacker, target_is_directory=True)
    return moved


class Hook:
    """Run ``action`` once, immediately before the real ``os.open`` of a given name."""

    def __init__(self, monkeypatch, name, action):
        self.real, self.done = os.open, False

        def wrapper(path, flags, mode=0o777, *, dir_fd=None):
            if not self.done and dir_fd is not None and path == name:
                self.done = True
                action()
            return self.real(path, flags, mode, dir_fd=dir_fd)

        monkeypatch.setattr(os, "open", wrapper)


# --------------------------------------------------- Finding 1: pre-existing links


def test_walk_refuses_a_symlink_at_every_component_position(tmp_path):
    base = private_dir(tmp_path / "walk")
    real = base / "real"
    (real / "b" / "c").mkdir(parents=True)
    # positions: first component, middle component, last component
    for position, make in {
        "first": lambda: (link_to(real, base / "a"), base / "a" / "b" / "c")[1],
        "middle": lambda: (
            (base / "m").mkdir(),
            link_to(real / "b", base / "m" / "b"),
            base / "m" / "b" / "c",
        )[2],
        "last": lambda: (
            (base / "l" / "b").mkdir(parents=True),
            link_to(real / "b" / "c", base / "l" / "b" / "c"),
            base / "l" / "b" / "c",
        )[2],
    }.items():
        with pytest.raises(UnsafePath) as caught:
            open_directory_nofollow(make())
        assert caught.value.symlink, position  # Linux reports ENOTDIR or ELOOP
    descriptor = open_directory_nofollow(real / "b" / "c")  # the plain path works
    os.close(descriptor)


def test_walk_reports_missing_and_non_directory_components(tmp_path):
    base = private_dir(tmp_path / "walk2")
    (base / "file").write_text("x")
    with pytest.raises(UnsafePath) as caught:
        open_directory_nofollow(base / "absent")
    assert caught.value.errno == errno.ENOENT and not caught.value.symlink
    with pytest.raises(UnsafePath) as caught:
        open_directory_nofollow(base / "file" / "x")
    assert caught.value.errno == errno.ENOTDIR and not caught.value.symlink


def test_symlinked_set_directory_and_set_parent_are_refused(world):
    set_dir = world.synthetic.set_dir
    final = link_to(set_dir, world.root / "set-final-link")
    parent = link_to(set_dir.parent, world.root / "set-parent-link")
    for via in (final, parent / set_dir.name):
        output, status = run(
            swap(verify_args(world.synthetic, world.key, world.manifest), "--set", via)
        )
        assert status == 1 and output["integrity"] == "integrity_invalid"
        assert output["reasons"][-1] == "set_member_symlink"
        assert "verified_references" not in output
    # and for generate: nothing is published
    target = private_dir(world.root / "gen-out")
    args = swap(
        generate_args(world.synthetic, world.key, target / "m.json"), "--set", parent / set_dir.name
    )
    output, status = run(args)
    assert status == 1 and output["publication"] == "not_published"
    assert list(target.iterdir()) == []


def test_symlinked_key_file_parent_is_refused(world):
    key_dir = world.key.path.parent
    via = link_to(key_dir, world.root / "key-parent-link") / world.key.path.name
    output, status = run(
        swap(verify_args(world.synthetic, world.key, world.manifest), "--recovery-key", via)
    )
    assert status == 1 and output["reasons"] == ["key_file_unsafe"]
    assert output["authenticity"] == "authenticity_invalid"
    deep = private_dir(world.root / "kd" / "inner")
    key = make_key(deep, installation_id=world.key.installation_id)
    outer = link_to(world.root / "kd", world.root / "kd-link")
    args = swap(
        verify_args(world.synthetic, world.key, world.manifest),
        "--recovery-key",
        outer / "inner" / key.path.name,
    )
    assert run(args)[0]["reasons"] == ["key_file_unsafe"]  # symlink at a grandparent position


def test_symlinked_manifest_parent_is_refused(world):
    via = link_to(world.manifest.parent, world.root / "manifest-parent-link") / world.manifest.name
    output, status = run(
        swap(verify_args(world.synthetic, world.key, world.manifest), "--manifest", via)
    )
    assert status == 1 and output["reasons"] == ["manifest_file_unsafe"]
    assert output["integrity"] == "integrity_invalid"


def test_symlinked_output_parent_is_refused_and_nothing_is_written(world):
    real = private_dir(world.root / "real-out")
    parent_link = link_to(real, world.root / "out-link")
    output, status = run(generate_args(world.synthetic, world.key, parent_link / "m.json"))
    assert status == 1 and output["reasons"] == ["output_unsafe"]
    assert output["publication"] == "not_published" and list(real.iterdir()) == []
    grand = private_dir(world.root / "g" / "inner")
    outer = link_to(world.root / "g", world.root / "g-link")
    output, status = run(generate_args(world.synthetic, world.key, outer / "inner" / "m.json"))
    assert output["reasons"] == ["output_unsafe"] and list(grand.iterdir()) == []


def test_stale_temporary_scan_does_not_follow_a_symlinked_directory(world):
    real = private_dir(world.root / "scan-real")
    write_private(real / f"{TEMP_PREFIX}abc", b"x")
    link = link_to(real, world.root / "scan-link")
    assert publish.stale_temporary_note(real) == ["stale_temporary_present"]
    assert publish.stale_temporary_note(link) == []


# --------------------------------------------------- Finding 1: swap after the open


def test_key_parent_swapped_between_walk_and_file_open_is_not_followed(world, monkeypatch):
    key_dir = world.key.path.parent
    original = world.key.path.read_bytes()
    attacker = private_dir(world.root / "attacker-key")
    forged = make_key(attacker, installation_id=world.key.installation_id)
    assert forged.path.name == world.key.path.name and forged.path.read_bytes() != original
    Hook(monkeypatch, world.key.path.name, lambda: replace_with_symlink(key_dir, attacker))
    data = read_protected_file(
        world.key.path, max_bytes=2048, unsafe_code="key_file_unsafe",
        too_large_code="key_file_unsafe", any_group_other_bit=True, require_owner=True,
    )  # fmt: skip
    assert data == original  # the pinned descriptor, not the swapped name, was used
    assert key_dir.is_symlink()  # the swap really happened


def test_manifest_parent_swapped_between_walk_and_file_open_is_not_followed(world, monkeypatch):
    directory = world.manifest.parent
    original = world.manifest.read_bytes()
    attacker = private_dir(world.root / "attacker-manifest")
    write_private(attacker / world.manifest.name, b'{"attacker":true}')
    Hook(monkeypatch, world.manifest.name, lambda: replace_with_symlink(directory, attacker))
    data = read_protected_file(
        world.manifest, max_bytes=4 * 1024 * 1024, unsafe_code="manifest_file_unsafe",
        too_large_code="manifest_too_large", any_group_other_bit=False, require_owner=False,
    )  # fmt: skip
    assert data == original and directory.is_symlink()


def test_set_directory_swapped_after_open_is_not_followed(world):
    set_dir = world.synthetic.set_dir
    attacker = private_dir(world.root / "attacker-set")
    write_private(attacker / "database.dump", b"attacker")
    with open_set(set_dir, LIMITS) as handle:
        replace_with_symlink(set_dir, attacker)
        scan = handle.scan(archive_declared=True)
        found = scan.sorted_found()
        assert [item.path for item in found][:1] == ["archive/.archive.json"] or found
        dump = next(item for item in found if item.path == "database.dump")
        digest, _ = handle.hash_member(dump, keep=False)
    assert dump.size != len(b"attacker") and len(digest) == 64 and not scan.violations


def test_output_parent_swapped_before_publication_is_not_followed(world, monkeypatch):
    out_dir = world.root / "swap-out"
    private_dir(out_dir)
    attacker = private_dir(world.root / "attacker-out")
    moved = {}

    def swap_now():
        moved["dir"] = replace_with_symlink(out_dir, attacker)

    state = publish_manifest(
        str(out_dir / "m.json"), b"{}", InjectedFaults({"before_publish": swap_now})
    )
    assert state == "published_durable" and out_dir.is_symlink()
    assert (moved["dir"] / "m.json").read_bytes() == b"{}"  # landed in the pinned directory
    assert list(attacker.iterdir()) == []  # nothing reached the attacker's directory
    assert not [p for p in moved["dir"].iterdir() if p.name.startswith(TEMP_PREFIX)]


def test_component_swapped_during_the_walk_is_refused_by_its_own_open(tmp_path, monkeypatch):
    base = private_dir(tmp_path / "race")
    (base / "a" / "b").mkdir(parents=True)
    attacker = private_dir(tmp_path / "attacker-walk")
    Hook(monkeypatch, "b", lambda: replace_with_symlink(base / "a" / "b", attacker))
    with pytest.raises(UnsafePath) as caught:
        open_directory_nofollow(base / "a" / "b")
    assert caught.value.symlink and caught.value.component == "b"


# --------------------------------------------------- Finding 1: descriptor cleanup


def test_no_descriptor_leaks_in_the_path_layer(world, tmp_path):
    base = private_dir(tmp_path / "fds")
    (base / "x" / "y").mkdir(parents=True)
    link_to(base / "x", base / "lx")
    started = open_descriptors()
    os.close(open_directory_nofollow(base / "x" / "y"))
    for bad in (base / "lx" / "y", base / "x" / "absent", base / "x" / "y" / "z"):
        with pytest.raises(UnsafePath):
            open_directory_nofollow(bad)
    kwargs = {
        "unsafe_code": "key_file_unsafe",
        "too_large_code": "key_file_unsafe",
        "any_group_other_bit": True,
        "require_owner": True,
    }
    read_protected_file(world.key.path, max_bytes=2048, **kwargs)
    for bad in (
        world.key.path.parent / "absent.key",
        world.root / "set-alias-missing" / "k",
        link_to(world.key.path.parent, base / "lk") / world.key.path.name,
    ):
        with pytest.raises(CodedError):
            read_protected_file(bad, max_bytes=2048, **kwargs)
    with pytest.raises(CodedError):
        read_protected_file(world.key.path, max_bytes=1, **kwargs)  # too large
    with open_set(world.synthetic.set_dir, LIMITS) as handle:
        handle.scan(archive_declared=True)
    for bad in (base / "lx", base / "absent", base / "x" / "y" / "z"):
        with pytest.raises(CodedError), open_set(bad, LIMITS):
            pass
    assert open_descriptors() == started


def test_no_descriptor_leaks_in_publication_on_any_path(world, tmp_path):
    started = open_descriptors()
    good = private_dir(tmp_path / "pub-good")
    assert publish_manifest(str(good / "m.json"), b"{}") == "published_durable"
    with pytest.raises(CodedError):  # output_exists
        publish_manifest(str(good / "m.json"), b"{}")
    writable = private_dir(tmp_path / "pub-writable")
    writable.chmod(0o770)
    with pytest.raises(CodedError):  # output_unsafe, parent group-writable
        publish_manifest(str(writable / "m.json"), b"{}")
    with pytest.raises(CodedError):  # symlinked parent
        publish_manifest(str(link_to(good, tmp_path / "pl") / "n.json"), b"{}")
    for point in (
        "before_temp_create",
        "mid_write",
        "before_flush",
        "after_flush",
        "before_publish",
    ):
        target = private_dir(tmp_path / f"pub-{point}")
        with pytest.raises((CodedError, OSError)):
            publish_manifest(
                str(target / "m.json"),
                b"{}",
                InjectedFaults({point: _raiser(OSError(errno.EIO, "x"))}),
            )
    for point in ("after_link", "before_dir_fsync"):
        target = private_dir(tmp_path / f"pub-{point}")
        state = publish_manifest(
            str(target / "m.json"), b"{}", InjectedFaults({point: _raiser(OSError(errno.EIO, "x"))})
        )
        assert state == "published_durability_uncertain"
    _, trust = parse_trust(
        generate_args(world.synthetic, world.key, tmp_path / "pub-good" / "g.json")
    )
    assert generate(trust).to_dict()["publication"] == "published_durable"
    assert open_descriptors() == started


def _raiser(error):
    def callback():
        raise error

    return callback


# --------------------------------------------------- Finding 2: temporary cleanup failure


def fail_temporary_unlink(monkeypatch):
    real = os.unlink

    def wrapper(path, *, dir_fd=None):
        if isinstance(path, str) and path.startswith(TEMP_PREFIX):
            raise OSError(errno.EIO, "injected unlink failure")
        return real(path, dir_fd=dir_fd)

    monkeypatch.setattr(os, "unlink", wrapper)
    return real


def run_generate(world, out_dir, name="m.json"):
    _, trust = parse_trust(generate_args(world.synthetic, world.key, out_dir / name))
    return generate(trust)


def test_unlink_failure_after_link_is_reported_not_swallowed(world, tmp_path, monkeypatch):
    out_dir = private_dir(tmp_path / "unlink")
    fail_temporary_unlink(monkeypatch)
    result = run_generate(world, out_dir)
    document = result.to_dict()
    final = out_dir / "m.json"
    temporaries = [p for p in out_dir.iterdir() if p.name.startswith(TEMP_PREFIX)]
    # the final manifest was published and flushed; it is never removed or replaced
    assert final.exists() and len(temporaries) == 1
    assert document["publication"] == "published_durable" and document["reasons"] == []
    # the surviving temporary is reported with the specified note (closed vocabulary, no name)
    assert document["notes"] == ["stale_temporary_present"]
    assert temporaries[0].name not in str(document)
    # it is a second hard link of the same bytes: link count 2, same inode
    info, temp_info = final.stat(), temporaries[0].stat()
    assert info.st_nlink == 2 and info.st_ino == temp_info.st_ino
    assert stat.S_IMODE(temp_info.st_mode) == 0o600
    # the verifier refuses the manifest while the link count is unsafe: not independently verifiable
    check, status = run(verify_args(world.synthetic, world.key, final))
    assert status == 1 and check["reasons"] == ["manifest_file_unsafe"]
    assert check["integrity"] == "integrity_invalid" and "verified_references" not in check
    assert check["notes"] == []
    # documented operator remediation: remove the leftover temporary, then verify
    monkeypatch.undo()
    temporaries[0].unlink()
    assert final.stat().st_nlink == 1
    check, status = run(verify_args(world.synthetic, world.key, final))
    assert status == 0 and check["reasons"] == [] and "verified_references" in check


def test_unlink_failure_is_listed_once_beside_an_existing_stale_note(world, tmp_path, monkeypatch):
    out_dir = private_dir(tmp_path / "unlink2")
    write_private(out_dir / f"{TEMP_PREFIX}abandoned", b"partial")
    fail_temporary_unlink(monkeypatch)
    document = run_generate(world, out_dir).to_dict()
    assert document["notes"] == ["stale_temporary_present"]  # no duplicate, still sorted


def test_unlink_failure_on_a_pre_publication_failure_is_also_reported(world, tmp_path, monkeypatch):
    out_dir = private_dir(tmp_path / "unlink3")
    fail_temporary_unlink(monkeypatch)
    _, trust = parse_trust(generate_args(world.synthetic, world.key, out_dir / "m.json"))
    result = generate(
        trust, faults=InjectedFaults({"before_flush": _raiser(OSError(errno.EIO, "x"))})
    )
    document = result.to_dict()
    assert document["publication"] == "not_published" and document["reasons"] == ["io_error"]
    assert document["notes"] == ["stale_temporary_present"]
    assert not (out_dir / "m.json").exists()


def test_ordinary_cleanup_leaves_no_temporary_and_no_note(world, tmp_path):
    out_dir = private_dir(tmp_path / "ordinary")
    document = run_generate(world, out_dir).to_dict()
    assert document["notes"] == [] and document["publication"] == "published_durable"
    assert sorted(p.name for p in out_dir.iterdir()) == ["m.json"]
    assert (out_dir / "m.json").stat().st_nlink == 1


def test_a_temporary_that_is_already_gone_is_not_an_error(tmp_path):
    out_dir = private_dir(tmp_path / "gone")
    report = {}
    descriptor = os.open(out_dir, os.O_RDONLY | os.O_DIRECTORY)
    try:
        publish._remove(descriptor, f"{TEMP_PREFIX}missing", report)
    finally:
        os.close(descriptor)
    assert report == {}


def test_remediation_is_documented_with_the_real_temporary_prefix():
    text = (Path(fsset.__file__).parents[3] / "docs" / "RECOVERY_SET.md").read_text()
    assert TEMP_PREFIX in text and "link count" in text and "stale_temporary_present" in text
    assert uuid.UUID(int=0)  # keep the import used
