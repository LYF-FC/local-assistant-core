# ruff: noqa: F811
"""Spec 074: the owner-approved metadata-only exception for the stage-1 overlap pre-check
(DECISIONS.md, 17 November 2026; spec section 2.5 post-freeze clarification). Synthetic data only.

What is approved, and what these tests hold the implementation to:

* A missing or malformed argument shape is rejected with zero filesystem access, even when the
  supplied paths would overlap (the strict A5 guards in ``test_recovery_set_verify`` are reused,
  not weakened, and no call count is tolerated).
* Only after every required argument is present and every shape is valid, the overlap pre-check
  (``cli._overlaps``) may make *metadata* calls to detect overlap and aliases: ``os.lstat`` and
  ``os.readlink`` (symlink resolution by ``posixpath.realpath``) and ``os.stat`` (same-file
  comparison by ``os.path.samestat``). It may not open, read, enumerate a directory's contents
  or write anything.
* An overlap rejection is still ``paths_overlap``, exit 2, with every state not evaluated.

The guards here record; the assertions classify what was recorded. The controls at the end prove
that a prohibited content read, enumeration, write, or metadata access moved before validation is
detected by the same assertions.
"""

import hashlib
import os
import stat as stat_module

import pytest
from recovery_set_support import (  # noqa: F401
    describe_calls,
    file_access_guards,
    generate_args,
    verify_args,
    world,
)
from test_recovery_set_verify import (
    GENERATE_REQUIRED,
    LOCALE_ENVIRONMENTS,
    VERIFY_REQUIRED,
    a5_arguments,
    malformed_cases,
    set_locale_environment,
)

from app.recovery_set import cli
from app.recovery_set.cli import run

NOT_EVALUATED = {
    "integrity": "integrity_not_evaluated",
    "authenticity": "authenticity_not_evaluated",
    "expectations": "expectations_not_evaluated",
    "freshness": "freshness_not_evaluated",
}
# Metadata operations the approved exception permits, and the only helpers that may make them.
ALLOWED_KINDS = {
    "os.lstat": {"_spellings"},
    "os.readlink": {"_spellings"},
    "os.stat": {"_same_existing_file"},
}
MUTATION_NAMES = (
    "write", "pwrite", "truncate", "ftruncate", "mkdir", "rename", "replace", "unlink", "remove",
    "rmdir", "link", "symlink", "chmod", "chown", "utime", "fsync", "fdatasync", "mkfifo",
    "mknod", "sendfile", "copy_file_range",
)  # fmt: skip


class _Mutations(list):
    pass


def mutation_guards():
    """Record (never refuse) any call of an ``os`` function that writes or changes the tree.

    ``file_access_guards`` covers reads, opens, metadata and enumeration; this covers the write
    side that it does not intercept. Installed by the test after fixture setup.
    """
    import contextlib

    @contextlib.contextmanager
    def guard():
        recorded = _Mutations()
        with pytest.MonkeyPatch.context() as patch:
            for name in MUTATION_NAMES:
                real = getattr(os, name, None)
                if real is None:
                    continue

                def make(label, function):
                    def recording(*args, **kwargs):
                        recorded.append(label)
                        return function(*args, **kwargs)

                    return recording

                patch.setattr(os, name, make(f"os.{name}", real))
            yield recorded

    return guard()


def assert_metadata_only(calls, mutations):
    """The recorded calls are exactly the approved metadata operations from the approved helpers."""
    assert not mutations, f"write-side calls during overlap checking: {mutations}"
    for kind, _, frames in calls:
        assert kind in ALLOWED_KINDS, (
            f"prohibited access {kind} (content read, open or enumeration):\n"
            + describe_calls(calls)
        )
        helpers = {function for name, function, _ in frames if name.endswith("recovery_set/cli.py")}
        assert helpers & ALLOWED_KINDS[kind], (
            f"{kind} not made by an approved overlap helper:\n" + describe_calls(calls)
        )


def snapshot(root):
    """Names, types, sizes, times, inodes, link counts, symlink targets and content hashes."""
    state = {}
    for directory, directories, files in os.walk(root):
        for name in sorted(directories + files):
            path = os.path.join(directory, name)
            info = os.lstat(path)
            entry = [stat_module.S_IFMT(info.st_mode), info.st_size, info.st_mtime_ns, info.st_ino]
            entry.append(info.st_nlink)
            if stat_module.S_ISLNK(info.st_mode):
                entry.append(os.readlink(path))
            elif stat_module.S_ISREG(info.st_mode):
                with open(path, "rb") as handle:
                    entry.append(hashlib.sha256(handle.read()).hexdigest())
            state[os.path.relpath(path, root)] = tuple(entry)
    return state


def swapped(args, flag, value):
    args = list(args)
    args[args.index(flag) + 1] = str(value)
    return args


def overlap_cases(world):
    """name -> arguments that pass every shape check and overlap by one mechanism."""
    set_dir = world.synthetic.set_dir
    key = world.key.path
    root = world.root
    verify = verify_args(world.synthetic, world.key, world.manifest)
    generate = generate_args(world.synthetic, world.key, world.out_dir / "new-manifest")
    link = root / "alias-of-set"
    link.symlink_to(set_dir, target_is_directory=True)
    file_link = root / "looks-outside.json"
    file_link.symlink_to(set_dir / "database.dump")
    hard = root / "hardlink-of-key"
    os.link(key, hard)
    return {
        "manifest-inside-set": swapped(verify, "--manifest", set_dir / "manifest.json"),
        "manifest-dotdot-inside-set": swapped(
            verify, "--manifest", f"{set_dir}/archive/../manifest.json"
        ),
        "manifest-is-the-set-directory": swapped(verify, "--manifest", set_dir),
        "key-inside-set": swapped(verify, "--recovery-key", set_dir / "recovery.key"),
        "key-equals-manifest": swapped(verify, "--manifest", key),
        "manifest-through-symlinked-parent": swapped(verify, "--manifest", link / "m.json"),
        "manifest-is-a-symlink-into-set": swapped(verify, "--manifest", file_link),
        "set-given-as-symlink": swapped(
            swapped(verify, "--set", link), "--manifest", set_dir / "m.json"
        ),
        "manifest-hard-links-the-key": swapped(verify, "--manifest", hard),
        "output-inside-set": swapped(generate, "--output", set_dir / "manifest.json"),
        "output-equals-key": swapped(generate, "--output", key),
        "output-through-symlinked-parent": swapped(generate, "--output", link / "m.json"),
    }


CASE_NAMES = [
    "manifest-inside-set",
    "manifest-dotdot-inside-set",
    "manifest-is-the-set-directory",
    "key-inside-set",
    "key-equals-manifest",
    "manifest-through-symlinked-parent",
    "manifest-is-a-symlink-into-set",
    "set-given-as-symlink",
    "manifest-hard-links-the-key",
    "output-inside-set",
    "output-equals-key",
    "output-through-symlinked-parent",
]


# ------------------------------------------------ shape validation precedes any metadata access


def overlapping(args):
    """The same arguments with the key (else the manifest/output) placed inside ``SET``, so that
    the paths would be rejected as overlapping if the shapes were valid."""
    args = list(args)
    set_dir = args[args.index("--set") + 1] if "--set" in args else None
    if set_dir is None:
        return args
    for flag, name in (("--recovery-key", "k.key"), ("--manifest", "m"), ("--output", "o")):
        if flag in args:
            args[args.index(flag) + 1] = f"{set_dir}/{name}"
            break
    return args


def strict_zero_access(world, args, reason):
    """The strict A5 assertion: zero guarded calls of any kind, closed code, nothing published."""
    listing = sorted(path.name for path in world.out_dir.iterdir())
    with file_access_guards(raising=False) as (counts, _, calls):
        output, status = run(args)
    assert dict(counts) == {}, (dict(counts), describe_calls(calls))
    assert status == 2 and output["reasons"] == [reason], output
    assert {key: output[key] for key in NOT_EVALUATED} == NOT_EVALUATED
    assert sorted(path.name for path in world.out_dir.iterdir()) == listing


@pytest.mark.parametrize("locale_name", sorted(LOCALE_ENVIRONMENTS))
@pytest.mark.parametrize(
    ("operation", "flag"),
    [("generate", flag) for flag in GENERATE_REQUIRED]
    + [("verify", flag) for flag in VERIFY_REQUIRED],
)
def test_a_missing_input_makes_no_filesystem_access_even_if_the_paths_overlap(
    world, monkeypatch, operation, flag, locale_name
):
    args = a5_arguments(world, operation)
    del args[args.index(flag) : args.index(flag) + 2]
    args = overlapping(args)
    set_locale_environment(monkeypatch, locale_name)
    strict_zero_access(world, args, "trust_input_missing")


@pytest.mark.parametrize("locale_name", sorted(LOCALE_ENVIRONMENTS))
@pytest.mark.parametrize(
    ("operation", "label", "mutate"),
    malformed_cases(),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_a_malformed_input_makes_no_filesystem_access_even_if_the_paths_overlap(
    world, monkeypatch, operation, label, mutate, locale_name
):
    args = overlapping(mutate(a5_arguments(world, operation)))
    set_locale_environment(monkeypatch, locale_name)
    strict_zero_access(world, args, "trust_input_malformed")


@pytest.mark.parametrize("locale_name", sorted(LOCALE_ENVIRONMENTS))
def test_a_freshness_without_a_hash_makes_no_filesystem_access_even_if_the_paths_overlap(
    world, monkeypatch, locale_name
):
    args = overlapping([*a5_arguments(world, "verify"), "--require-freshness"])
    set_locale_environment(monkeypatch, locale_name)
    strict_zero_access(world, args, "freshness_requested_without_expected_hash")


def test_a_the_overlap_precheck_runs_only_after_every_shape_is_valid(world, monkeypatch):
    """``cli._overlaps`` is reached exactly once for valid shapes and never for an invalid shape."""
    reached = []
    real = cli._overlaps
    monkeypatch.setattr(cli, "_overlaps", lambda *a: reached.append(a) or real(*a))
    invalid = []
    for operation, flags in (("generate", GENERATE_REQUIRED), ("verify", VERIFY_REQUIRED)):
        for flag in flags:
            args = a5_arguments(world, operation)
            del args[args.index(flag) : args.index(flag) + 2]
            invalid.append(overlapping(args))
        for _, _, mutate in [case for case in malformed_cases() if case[0] == operation]:
            invalid.append(overlapping(mutate(a5_arguments(world, operation))))
    invalid.append(overlapping([*a5_arguments(world, "verify"), "--require-freshness"]))
    for args in invalid:
        output, status = run(args)
        assert status == 2 and output["reasons"] != ["paths_overlap"], (args, output)
    assert reached == []
    output, status = run(
        swapped(a5_arguments(world, "verify"), "--manifest", world.synthetic.set_dir / "m")
    )
    assert status == 2 and output["reasons"] == ["paths_overlap"]
    assert len(reached) == 1
    assert run(a5_arguments(world, "verify"))[1] == 0
    assert len(reached) == 2


# ------------------------------------------- the overlap rejection is metadata-only and inert


@pytest.mark.parametrize("name", CASE_NAMES)
def test_a_overlap_rejection_is_paths_overlap_and_only_reads_metadata(world, name):
    args = overlap_cases(world)[name]
    before = snapshot(world.root)
    with mutation_guards() as mutations, file_access_guards(raising=False) as (_, _, calls):
        output, status = run(args)
    after = snapshot(world.root)
    assert status == 2 and output["reasons"] == ["paths_overlap"], output
    assert {key: output[key] for key in NOT_EVALUATED} == NOT_EVALUATED
    if args[0] == "generate":
        assert output["publication"] == "not_published"
        assert not (world.out_dir / "new-manifest").exists()
    assert calls, "the overlap pre-check made no metadata call: the guard would prove nothing"
    assert_metadata_only(calls, mutations)
    assert before == after, "an overlap rejection changed the filesystem or a file's contents"


def test_a_symlink_resolution_and_same_file_comparison_are_the_permitted_operations(world):
    cases = overlap_cases(world)
    kinds = {}
    for name in ("manifest-through-symlinked-parent", "manifest-hard-links-the-key"):
        with file_access_guards(raising=False) as (_, _, calls):
            run(cases[name])
        kinds[name] = {kind for kind, _, _ in calls}
    assert kinds["manifest-through-symlinked-parent"] == {"os.lstat", "os.readlink"}
    assert "os.stat" in kinds["manifest-hard-links-the-key"]


# ------------------------------- non-overlapping inputs still reach the protected reading path


def test_a_valid_non_overlapping_inputs_still_read_through_the_protected_path(world, monkeypatch):
    """Guard scoped to the pre-check only: it makes metadata calls alone; the rest of the run
    (outside the scope) opens and reads the authorized files as before."""
    scoped = {}
    real = cli._overlaps

    def scoped_precheck(*arguments):
        with mutation_guards() as mutations, file_access_guards(raising=False) as (_, _, calls):
            result = real(*arguments)
        scoped["calls"], scoped["mutations"], scoped["result"] = calls, mutations, result
        return result

    monkeypatch.setattr(cli, "_overlaps", scoped_precheck)
    with file_access_guards(raising=False) as (counts, origins, calls):
        output, status = run(verify_args(world.synthetic, world.key, world.manifest))
    assert status == 0 and output["integrity"] == "integrity_valid", output
    assert scoped["result"] is False and scoped["calls"]
    assert_metadata_only(scoped["calls"], scoped["mutations"])
    assert counts["os.open"] > 0 and counts["os.read"] > 0 and counts["os.fstat"] > 0
    assert origins["os.open"] > 0 and origins["os.read"] > 0
    first_open = next(index for index, call in enumerate(calls) if call[0] == "os.open")
    assert first_open >= len(scoped["calls"]), (
        "a protected open happened before the pre-check ended"
    )


def test_a_valid_generate_still_publishes_after_the_precheck(world):
    target = world.out_dir / "new-manifest"
    output, status = run(generate_args(world.synthetic, world.key, target))
    assert status == 0 and output["publication"] == "published_durable", output
    assert target.exists()


# --------------------------------------------------------------------------------- controls
# Each control weakens the implementation in one prohibited way and shows that the assertions
# above would catch it. They run against a copy of the behaviour (monkeypatched), never the code.


def run_with_guards(world, args):
    with mutation_guards() as mutations, file_access_guards(raising=False) as (_, _, calls):
        run(args)
    return calls, mutations


def test_a_control_a_content_read_during_overlap_checking_is_detected(world, monkeypatch):
    real = cli._same_existing_file

    def reading(first, second):
        with open(first, "rb") as handle:
            handle.read(1)
        return real(first, second)

    monkeypatch.setattr(cli, "_same_existing_file", reading)
    calls, mutations = run_with_guards(
        world, verify_args(world.synthetic, world.key, world.manifest)
    )
    assert {kind for kind, _, _ in calls} & {"builtins.open", "io.open"}
    with pytest.raises(AssertionError, match="prohibited access"):
        assert_metadata_only(calls, mutations)


def test_a_control_a_directory_enumeration_during_overlap_checking_is_detected(world, monkeypatch):
    real = cli._overlaps

    def enumerating(set_path, key_path, file_path):
        list(os.scandir(set_path))
        return real(set_path, key_path, file_path)

    monkeypatch.setattr(cli, "_overlaps", enumerating)
    calls, mutations = run_with_guards(
        world, verify_args(world.synthetic, world.key, world.manifest)
    )
    with pytest.raises(AssertionError, match="prohibited access"):
        assert_metadata_only(calls, mutations)


def test_a_control_a_write_during_overlap_checking_is_detected(world, monkeypatch):
    scratch = world.root / "scratch-for-the-control"
    scratch.write_bytes(b"synthetic")
    real = cli._overlaps

    def writing(set_path, key_path, file_path):
        os.utime(scratch, (1, 1))
        return real(set_path, key_path, file_path)

    monkeypatch.setattr(cli, "_overlaps", writing)
    calls, mutations = run_with_guards(
        world, verify_args(world.synthetic, world.key, world.manifest)
    )
    assert mutations == ["os.utime"]
    with pytest.raises(AssertionError, match="write-side"):
        assert_metadata_only(calls, mutations)
    # the snapshot comparison also sees the change
    assert os.lstat(scratch).st_mtime_ns == 1_000_000_000


def test_a_control_a_metadata_access_before_shape_validation_is_detected(world, monkeypatch):
    real = cli.parse_arguments

    def early(argv):
        os.lstat(".")  # a metadata call moved ahead of shape validation
        return real(argv)

    monkeypatch.setattr(cli, "parse_arguments", early)
    args = a5_arguments(world, "verify")
    del args[args.index("--manifest") : args.index("--manifest") + 2]
    with pytest.raises(AssertionError):
        strict_zero_access(world, args, "trust_input_missing")


def test_a_control_a_lexical_only_overlap_check_would_miss_a_symlink_alias(world, monkeypatch):
    """The permitted symlink resolution is what catches the alias; this shows it is exercised."""
    args = overlap_cases(world)["manifest-through-symlinked-parent"]
    monkeypatch.setattr(cli, "_spellings", lambda path: {os.path.abspath(path)})
    output, _ = run(args)
    assert output["reasons"] != ["paths_overlap"]
