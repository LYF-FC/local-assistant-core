# ruff: noqa: F811
"""Spec 074 Phase B review points A to D (synthetic data only).

A: ``paths_overlap`` is a stage-1 *path-shape* check. It covers lexical spellings and symlinked
   parents. It is not the symlink defence: the descriptor-relative opens are (tests below show
   both layers).
B: ``manifest_hash`` is emitted exactly when it was computed from an authentic manifest.
C: set-stage ordering is deterministic and reports the first violation only.
D: fault injection is a function parameter that no operator input can reach.
"""

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from recovery_set_support import (  # noqa: F401
    build_world,
    generate_args,
    verify_args,
    world,
    write_private,
)

from app.recovery_set import cli, generate, publish
from app.recovery_set.cli import run
from app.recovery_set.result import KEYS

PACKAGE = Path(cli.__file__).parent


def out(arguments):
    return run(arguments)


def swap(args, flag, value):
    args = list(args)
    args[args.index(flag) + 1] = str(value)
    return args


# ---------------------------------------------------------------- A: paths_overlap


def overlap(world, flag, value, *, generate_mode=False):
    if generate_mode:
        args = generate_args(world.synthetic, world.key, world.root / "free" / "m.json")
    else:
        args = verify_args(world.synthetic, world.key, world.manifest)
    output, status = out(swap(args, flag, value))
    return output, status


def assert_refused(result):
    output, status = result
    assert status == 2 and output["reasons"] == ["paths_overlap"]
    assert output["integrity"] == "integrity_not_evaluated"
    assert output["authenticity"] == "authenticity_not_evaluated"
    assert output["expectations"] == "expectations_not_evaluated"


def test_a_relative_paths_and_dotdot_components(world, monkeypatch):
    set_dir = world.synthetic.set_dir
    monkeypatch.chdir(set_dir.parent)
    relative = os.path.relpath(set_dir)
    for spelling in (
        f"{relative}/manifest.json",
        f"{relative}/archive/../manifest.json",
        f"./{relative}/./x/../manifest.json",
        f"{relative}/../{relative}/manifest.json",
    ):
        assert_refused(overlap(world, "--manifest", spelling))
    monkeypatch.chdir(set_dir)  # SET given relative, file given absolute inside it
    args = swap(verify_args(world.synthetic, world.key, world.manifest), "--set", ".")
    assert_refused(out(swap(args, "--manifest", set_dir / "m.json")))


def test_a_redundant_separators_and_alternate_spellings(world):
    set_dir = str(world.synthetic.set_dir)
    for spelling in (
        set_dir + "//manifest.json",
        set_dir + "/./manifest.json",
        set_dir + "///archive//x",
        set_dir + "/",  # the SET directory itself
    ):
        assert_refused(overlap(world, "--manifest", spelling))
        assert_refused(overlap(world, "--recovery-key", spelling))
    # SET itself spelled with redundant parts
    args = verify_args(world.synthetic, world.key, set_dir + "/m")
    assert_refused(out(swap(args, "--set", set_dir + "/./")))


def test_a_symlinked_parent_into_set_is_refused(world):
    link = world.root / "alias-of-set"
    link.symlink_to(world.synthetic.set_dir, target_is_directory=True)
    assert_refused(overlap(world, "--manifest", link / "new-manifest.json"))
    assert_refused(overlap(world, "--recovery-key", link / "new.key"))
    assert_refused(overlap(world, "--output", link / "new-manifest.json", generate_mode=True))
    # a symlink into a subdirectory of SET, and a chain of two links
    inner = world.root / "alias-of-archive"
    inner.symlink_to(world.synthetic.set_dir / "archive", target_is_directory=True)
    assert_refused(overlap(world, "--manifest", inner / "m.json"))
    chain = world.root / "chain"
    chain.symlink_to(link, target_is_directory=True)
    assert_refused(overlap(world, "--manifest", chain / "m.json"))


def test_a_symlinked_set_argument_is_resolved(world):
    link = world.root / "set-alias"
    link.symlink_to(world.synthetic.set_dir, target_is_directory=True)
    args = swap(verify_args(world.synthetic, world.key, world.manifest), "--set", link)
    inside_real = world.synthetic.set_dir / "m.json"
    assert_refused(out(swap(args, "--manifest", inside_real)))


def test_a_file_symlink_that_resolves_into_set_is_refused(world):
    target = world.synthetic.set_dir / "database.dump"
    link = world.root / "looks-outside.json"
    link.symlink_to(target)
    assert_refused(overlap(world, "--manifest", link))


def test_a_key_and_manifest_overlap_by_any_spelling(world):
    key = world.key.path
    assert_refused(overlap(world, "--manifest", key))
    assert_refused(overlap(world, "--manifest", f"{key.parent}/./{key.name}"))
    assert_refused(overlap(world, "--manifest", f"{key.parent}/../{key.parent.name}/{key.name}"))
    link_dir = world.root / "key-dir-alias"
    link_dir.symlink_to(key.parent, target_is_directory=True)
    assert_refused(overlap(world, "--manifest", link_dir / key.name))
    assert_refused(overlap(world, "--output", key, generate_mode=True))


def test_a_hard_link_to_the_key_is_the_same_file(world):
    alias = world.root / "hardlink-of-key"
    os.link(world.key.path, alias)
    assert_refused(overlap(world, "--manifest", alias))


def test_a_siblings_with_a_shared_prefix_do_not_overlap(world):
    sibling = Path(str(world.synthetic.set_dir) + "-sibling")
    sibling.mkdir(mode=0o700)
    output, status = overlap(world, "--manifest", sibling / "manifest.json")
    assert output["reasons"] != ["paths_overlap"]
    # a symlink to a directory that is NOT inside SET is not an overlap
    link = world.root / "elsewhere"
    link.symlink_to(world.out_dir, target_is_directory=True)
    output, status = overlap(world, "--manifest", link / world.manifest.name)
    assert output["reasons"] != ["paths_overlap"] and status != 2


def test_a_root_set_does_not_crash_the_containment_test():
    assert cli._inside("/etc/x", "/") and not cli._inside("/etc", "/etc/x")
    assert cli._inside("/etc/x", "/etc") and not cli._inside("/etcd/x", "/etc")


def test_a_lexical_check_alone_does_not_stop_a_later_symlink_swap(world):
    """Layering: after the stage-1 check passes, a manifest that is (or becomes) a symlink is
    still refused by the O_NOFOLLOW open, and a symlinked SET is refused by the set open."""
    real = world.manifest.with_name("real.json")
    real.write_bytes(world.manifest.read_bytes())
    real.chmod(0o600)
    world.manifest.unlink()
    world.manifest.symlink_to(real)
    output, status = world.verify()
    assert status == 1 and output["reasons"] == ["manifest_file_unsafe"]


def test_a_symlinked_set_root_is_refused_by_the_descriptor_open(world):
    link = world.root / "set-link"
    link.symlink_to(world.synthetic.set_dir, target_is_directory=True)
    args = swap(verify_args(world.synthetic, world.key, world.manifest), "--set", link)
    output, status = out(args)
    assert status == 1 and output["integrity"] == "integrity_invalid"
    assert output["reasons"][-1] in {"set_path_unsafe", "set_member_symlink"}


# ---------------------------------------------------------------- B: manifest_hash


def test_b_manifest_hash_present_whenever_authentic_even_if_other_checks_fail(world):
    good, status = world.verify()
    assert status == 0
    expected = good["manifest_hash"]
    # expectation failure: authentic, so the public reference is present
    bad, status = world.verify(installation="00000000-0000-4000-8000-000000000000")
    assert status == 1 and bad["authenticity"] == "authenticity_valid"
    assert bad["manifest_hash"] == expected and "verified_references" not in bad
    # set failure: authentic, so present, and still no verified_references
    dump = world.synthetic.set_dir / "database.dump"
    dump.write_bytes(dump.read_bytes()[:-1] + b"X")
    bad, status = world.verify()
    assert bad["integrity"] == "integrity_invalid" and bad["manifest_hash"] == expected
    assert "verified_references" not in bad


def test_b_manifest_hash_absent_when_authenticity_is_not_established(world):
    # every failure at or before the MAC check
    world.manifest.write_text("{bad")
    assert "manifest_hash" not in world.verify()[0]
    fresh = build_world(world.root.parent / "b2")
    fresh.rewrite(lambda d: d.update(mac="0" * 64), resign=False)
    assert "manifest_hash" not in fresh.verify()[0]
    other = build_world(world.root.parent / "b3")
    wrong = swap(
        verify_args(other.synthetic, other.key, other.manifest),
        "--expected-key-fingerprint",
        "0" * 64,
    )
    output, status = out(wrong)
    assert output["reasons"] == ["key_fingerprint_mismatch"] and "manifest_hash" not in output
    usage, status = out(["verify"])
    assert status == 2 and "manifest_hash" not in usage


def test_b_manifest_hash_is_a_public_reference_not_verified_references(world):
    output, _ = world.verify()
    assert output["verified_references"]["manifest_hash"] == output["manifest_hash"]
    dump = world.synthetic.set_dir / "database.dump"
    dump.write_bytes(b"x" + dump.read_bytes()[1:])
    bad, _ = world.verify()
    assert "manifest_hash" in bad and "verified_references" not in bad


def test_b_generate_reports_hash_only_when_it_produced_a_manifest_body(world, tmp_path):
    target = world.root / "free"
    target.mkdir(mode=0o700, exist_ok=True)
    ok, status = out(generate_args(world.synthetic, world.key, target / "m.json"))
    assert status == 0 and re.fullmatch(r"[0-9a-f]{64}", ok["manifest_hash"])
    wrong = swap(
        generate_args(world.synthetic, world.key, target / "m2.json"),
        "--expected-key-fingerprint", "0" * 64,
    )  # fmt: skip
    output, status = out(wrong)
    assert status == 1 and "manifest_hash" not in output


# ---------------------------------------------------------------- C: ordering


def test_c_expectation_reasons_precede_set_reasons_in_a_fixed_order(world):
    dump = world.synthetic.set_dir / "database.dump"
    dump.write_bytes(dump.read_bytes()[:-1] + b"X")  # set_member_hash_mismatch
    output, status = world.verify(
        installation="00000000-0000-4000-8000-000000000000",
        head="0001_not_the_head",
        expect="absent",
    )
    assert status == 1
    assert output["reasons"][:3] == [
        "installation_mismatch",
        "schema_head_mismatch",
        "archive_expectation_mismatch",
    ]
    # exactly one set-stage reason follows, and it comes after every expectation reason
    assert len(output["reasons"]) == 4 and output["reasons"][3].startswith(("set_", "archive_"))
    assert output["expectations"] == "expectations_not_met"
    assert output["integrity"] == "integrity_invalid"


def test_c_archive_expectation_mismatch_is_before_any_set_violation(world):
    (world.synthetic.set_dir / "stray.txt").write_bytes(b"x")  # set_member_unexpected
    output, _ = world.verify(expect="absent")
    assert output["reasons"][0] == "archive_expectation_mismatch"
    assert len(output["reasons"]) == 2 and output["reasons"][1].startswith("set_")


def test_c_only_the_first_set_violation_is_reported_in_detection_order(world):
    set_dir = world.synthetic.set_dir
    set_dir.chmod(0o750)  # first in detection order: SET mode
    (set_dir / "zz-stray.txt").write_bytes(b"x")  # then an unexpected member
    dump = set_dir / "database.dump"
    dump.write_bytes(dump.read_bytes()[:-1] + b"X")  # hashing is never reached
    output, status = world.verify()
    assert status == 1 and output["reasons"] == ["set_member_unsafe_mode"]
    set_dir.chmod(0o700)
    output, _ = world.verify()
    assert output["reasons"] == ["set_member_unexpected"]  # structure before hashing
    (set_dir / "zz-stray.txt").unlink()
    output, _ = world.verify()
    assert output["reasons"] == ["set_member_hash_mismatch"]


def test_c_result_is_independent_of_creation_order_and_repeatable(tmp_path):
    results = []
    for number, names in enumerate((("b.txt", "a.txt", "c.txt"), ("c.txt", "b.txt", "a.txt"))):
        built = build_world(tmp_path / f"order{number}")
        for name in names:
            (built.synthetic.set_dir / name).write_bytes(b"x")
        results.append([built.verify()[0] for _ in range(2)])
    stripped = [
        [{k: v for k, v in item.items() if k != "elapsed_ms"} for item in pair] for pair in results
    ]
    flat = [item for pair in stripped for item in pair]
    # same synthetic content but different set ids: compare the failure shape only
    assert {tuple(item["reasons"]) for item in flat} == {("set_member_unexpected",)}


def test_c_no_count_of_further_violations_is_emitted(world):
    """Spec 3.4 mentions "a count of further violations only"; the closed key set of 7.3 has no
    such key and may not be extended, so none is emitted. Recorded for the owner (report)."""
    set_dir = world.synthetic.set_dir
    for name in ("s1.txt", "s2.txt"):
        (set_dir / name).write_bytes(b"x")
    output, _ = world.verify()
    assert set(output) <= set(KEYS) and output["reasons"] == ["set_member_unexpected"]
    assert not any("count" in key and key != "member_count" for key in output)


# ---------------------------------------------------------------- D: fault injection


def test_d_fault_injection_is_not_named_anywhere_an_operator_can_reach():
    for name in ("cli.py", "__main__.py", "__init__.py"):
        text = (PACKAGE / name).read_text()
        for word in ("InjectedFaults", "faults", "after_link", "set_id", "created_at"):
            assert word not in text, (name, word)
    for source in PACKAGE.glob("*.py"):
        text = source.read_text()
        assert "os.environ" not in text and "getenv" not in text, source.name
        assert "argparse" not in text or source.name == "cli.py"


def test_d_cli_calls_the_operations_with_trust_inputs_only():
    tree = ast.parse((PACKAGE / "cli.py").read_text())
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"generate", "verify"}
    ]
    assert calls and all(len(call.args) == 1 and not call.keywords for call in calls)


def test_d_test_only_parameters_default_to_off():
    import inspect

    for function, names in (
        (generate.generate, ("faults", "set_id", "created_at", "chain")),
        (publish.publish_manifest, ("faults",)),
    ):
        parameters = inspect.signature(function).parameters
        assert all(parameters[name].default is None for name in names)


def test_d_environment_and_flags_cannot_activate_a_fault(world, tmp_path):
    target = tmp_path / "free"
    target.mkdir(mode=0o700)
    environment = {
        **os.environ,
        "PYTHONPATH": str(Path(cli.__file__).parents[2]),
        **{
            name: "after_link"
            for name in (
                "BUTLER_RECOVERY_SET_FAULT", "RECOVERY_SET_FAULT", "FAULT", "FAULTS",
                "BUTLER_FAULT_INJECTION", "BUTLER_TEST_FAULT", "AFTER_LINK",
            )
        },
    }  # fmt: skip
    args = generate_args(world.synthetic, world.key, target / "m.json")
    done = subprocess.run(
        [sys.executable, "-m", "app.recovery_set", *args],
        env=environment, capture_output=True, text=True, timeout=60, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stdout
    assert '"publication":"published_durable"' in done.stdout.replace(" ", "")
    for flag in ("--fault", "--inject-fault", "--after-link", "--faults"):
        output, status = out([*args, flag, "after_link"])
        assert status == 2 and output["reasons"] == ["trust_input_malformed"]


def test_d_after_link_keeps_no_replace_and_never_claims_durability(world, tmp_path):
    from app.recovery_set.publish import InjectedFaults, publish_manifest

    target = tmp_path / "pub"
    target.mkdir(mode=0o700)
    final = target / "m.json"

    def boom():
        raise OSError("injected")

    state = publish_manifest(str(final), b"{}", InjectedFaults({"after_link": boom}))
    assert state == "published_durability_uncertain" and final.read_bytes() == b"{}"
    from app.recovery_set.format import CodedError

    with pytest.raises(CodedError) as caught:
        publish_manifest(str(final), b"other", None)
    assert caught.value.code == "output_exists" and final.read_bytes() == b"{}"


def test_d_without_faults_behaviour_is_unchanged(tmp_path):
    from app.recovery_set.publish import publish_manifest

    target = tmp_path / "pub"
    target.mkdir(mode=0o700)
    assert publish_manifest(str(target / "m.json"), b"{}", None) == "published_durable"
    assert sorted(item.name for item in target.iterdir()) == ["m.json"]
