# ruff: noqa: F811
"""Spec 074 B030 to B032 and B043: verification flow, state model, freshness precedence,
trust inputs, output allowlist (T1, T17 to T23, T25, T26, T32 to T34, T44 to T48, T53, T54)."""

import base64
import json
import logging
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from recovery_set_support import (  # noqa: F401
    AccessAttempted,
    bare_world,
    build_world,
    describe_calls,
    file_access_guards,
    make_key,
    private_dir,
    run_generate,
    verify_args,
    world,
    write_private,
)

from app.recovery_set import verify as verify_module
from app.recovery_set.cli import run
from app.recovery_set.format import CodedError
from app.recovery_set.result import (
    AUTHENTICITY,
    EXPECTATIONS,
    FRESHNESS,
    INTEGRITY,
    KEYS,
    VERIFIED_KEYS,
)
from app.recovery_set.verify import verifier_chain

STATES = (
    "integrity_not_evaluated",
    "authenticity_not_evaluated",
    "expectations_not_evaluated",
    "freshness_not_evaluated",
)


def reasons(output):
    return output["reasons"]


def states(output):
    return tuple(
        output[name] for name in ("integrity", "authenticity", "expectations", "freshness")
    )


def check_closed(output):
    assert set(output) <= KEYS
    assert output["integrity"] in INTEGRITY and output["authenticity"] in AUTHENTICITY
    assert output["expectations"] in EXPECTATIONS and output["freshness"] in FRESHNESS
    assert output["point_in_time"] is True
    assert output["restore_performed"] is False and output["recovery_complete"] is False
    text = json.dumps(output).replace("freshness_", "FRESHNESSTOKEN_")
    assert not re.search(r"\b(latest|current|fresh|up to date)\b", text, re.IGNORECASE)
    if "verified_references" in output:
        assert set(output["verified_references"]) == VERIFIED_KEYS
    return output


def key_forms(material):
    """Raw key bytes plus hex, uppercase hex, base64, URL-safe base64 and repr forms."""
    raw = bytes.fromhex(material)
    return [
        raw,
        material.encode(),
        material.upper().encode(),
        base64.b64encode(raw),
        base64.urlsafe_b64encode(raw),
        repr(raw).encode(),
    ]


def fresh(world, name):
    return build_world(world.root.parent / name)


def test_t1_valid_set_and_a1_outcome(world):
    output, status = world.verify()
    check_closed(output)
    assert status == 0 and reasons(output) == [] and output["notes"] == []
    assert states(output) == (
        "integrity_valid",
        "authenticity_valid",
        "expectations_met",
        "freshness_not_evaluated",
    )
    assert output["member_count"] == 6 and output["operation"] == "verify"
    assert "freshness_note" not in output and "publication" not in output


def test_bare_set_without_archive_verifies(bare_world):
    output, status = bare_world.verify()
    assert status == 0 and output["member_count"] == 1


def test_t17_key_bound_to_other_installation_than_the_manifest_declares(world):
    other = make_key(world.root / "k2")  # a different installation id
    declared = world.load()["payload"]["body"]["installation"]["installation_id"]
    assert other.installation_id != declared

    def mutate(document):
        document["payload"]["key_id"] = other.key_id
        document["payload"]["key_fingerprint"] = other.fingerprint()

    world.rewrite(mutate, key=other)  # the MAC is valid under that key
    output, status = run(verify_args(world.synthetic, other, world.manifest, installation=declared))
    assert status == 1 and reasons(output) == ["key_installation_mismatch"]
    assert states(output) == (
        "integrity_not_evaluated",
        "authenticity_invalid",
        "expectations_not_evaluated",
        "freshness_not_evaluated",
    )


def test_t18_key_and_manifest_bound_to_b_expected_a(tmp_path):
    installation_b = str(uuid.uuid4())
    root = private_dir(tmp_path / "b")
    from recovery_set_support import make_set

    synthetic = make_set(root / "s")
    key = make_key(root / "k", installation_id=installation_b)
    manifest = private_dir(root / "o") / "m"
    assert run_generate(synthetic, key, manifest)[1] == 0
    expected_a = str(uuid.uuid4())
    output, status = run(verify_args(synthetic, key, manifest, installation=expected_a))
    assert status == 1 and reasons(output) == ["installation_mismatch"]
    assert states(output) == (
        "integrity_valid",
        "authenticity_valid",
        "expectations_not_met",
        "freshness_not_evaluated",
    )
    assert "verified_references" not in output


def test_t19_schema_expectations(world):
    chain = verifier_chain()
    output = world.verify(head=chain[-2])[0]
    assert "schema_head_mismatch" in reasons(output)
    assert states(output)[2] == "expectations_not_met" and states(output)[0] == "integrity_valid"
    cases = {
        "schema_chain_inconsistent": lambda d: d["payload"]["body"]["schema"].update(
            revisions=[*chain, chain[-1]]
        ),
        "schema_unknown_to_verifier": lambda d: d["payload"]["body"]["schema"].update(
            head="9999_unknown_future", revisions=[*chain, "9999_unknown_future"]
        ),
    }
    for number, (code, mutate) in enumerate(cases.items()):
        other = fresh(world, f"s{number}")
        other.rewrite(mutate)
        head = "9999_unknown_future" if "unknown" in code else chain[-1]
        output = other.verify(head=head)[0]
        assert code in reasons(output), (code, reasons(output))
        assert states(output)[2] == "expectations_not_met"
    wrong_tail = fresh(world, "tail")
    wrong_tail.rewrite(
        lambda d: d["payload"]["body"]["schema"].update(revisions=[chain[-1], chain[0]])
    )
    assert "schema_chain_inconsistent" in reasons(wrong_tail.verify()[0])
    older = fresh(world, "older")  # an older head is allowed when it is a prefix of the chain
    older.rewrite(
        lambda d: d["payload"]["body"]["schema"].update(head=chain[3], revisions=list(chain[:4]))
    )
    assert older.verify(head=chain[3])[1] == 0


def test_t20_require_freshness_needs_a_hash_and_reads_nothing(tmp_path):
    missing = ["--manifest", str(tmp_path / "x"), "--recovery-key", str(tmp_path / "y")]
    args = verify_args(
        type("S", (), {"set_dir": tmp_path / "z", "archive": True})(),
        type(
            "K",
            (),
            {
                "path": tmp_path / "y",
                "fingerprint": lambda self: "a" * 64,
                "installation_id": str(uuid.uuid4()),
            },
        )(),
        tmp_path / "x",
        extra=["--require-freshness"],
    )
    output, status = run(args)
    assert status == 2 and reasons(output) == ["freshness_requested_without_expected_hash"]
    assert states(output) == STATES and missing


def test_t20_with_a_hash_the_flag_adds_no_other_condition(world):
    output, status = world.verify(
        extra=["--expected-manifest-hash", world.hash(), "--require-freshness"]
    )
    assert status == 0 and reasons(output) == [] and output["freshness"] == "freshness_match"


def second_manifest(world):
    path = world.out_dir / "newer.json"
    assert run_generate(world.synthetic, world.key, path)[1] == 0
    document = json.loads(path.read_bytes())
    from app.recovery_set.format import manifest_hash

    return manifest_hash(document["payload"])


def test_t21_older_authenticated_manifest_without_hash(world):
    second_manifest(world)
    output, status = world.verify()
    assert status == 0 and output["freshness"] == "freshness_not_evaluated"
    assert reasons(output) == []


@pytest.mark.parametrize("require", [False, True])
def test_t22_older_manifest_with_newer_hash(world, require):
    newer = second_manifest(world)
    extra = ["--expected-manifest-hash", newer] + (["--require-freshness"] if require else [])
    output, status = world.verify(extra=extra)
    assert status == 1 and output["freshness"] == "freshness_mismatch"
    expected = ["freshness_expected_hash_mismatch"]
    if require:  # the flag adds a reason but never turns a supplied mismatch into a pass
        expected.append("freshness_required_not_established")
    assert reasons(output) == expected
    assert (
        output["integrity"] == "integrity_valid" and output["authenticity"] == "authenticity_valid"
    )


def test_t23_matching_expected_hash(world):
    output, status = world.verify(extra=["--expected-manifest-hash", world.hash()])
    check_closed(output)
    assert status == 0 and output["freshness"] == "freshness_match"
    assert output["freshness_note"] == "matches_supplied_expected_hash_only"
    assert output["manifest_hash"] == world.hash()


def test_t25_cross_installation_substitution(tmp_path):
    """T25: a complete valid set and manifest for installation B presented for installation A.

    The assertions record the exact outcome of each of the three scenarios (reason, the four
    states, exit status, no ``verified_references``, empty ``notes``) and, as a control, that
    ``manifest_key_reference_mismatch`` is reachable only for a different key bound to the
    declared installation. They match the T25 row as corrected by the owner's decision of
    16 November 2026 (DECISIONS.md): scenario 2, installation A's key and fingerprint with
    installation B's manifest, reports ``key_installation_mismatch``, because the key's
    installation binding is checked before the key references and the MAC (2.5, 6.2, 7.2 step 3
    and T17). The frozen T25 text had listed ``manifest_authentication_failed`` or
    ``manifest_key_reference_mismatch`` for that scenario; that one cell was corrected after the
    freeze, and the verification order and the code were not changed. The test shows these
    outcomes in process with synthetic keys only; it shows no other key or manifest pairing.
    """
    from recovery_set_support import make_set

    root = private_dir(tmp_path / "b")
    b_set = make_set(root / "s")
    key_b = make_key(root / "kb")
    manifest = private_dir(root / "o") / "m"
    assert run_generate(b_set, key_b, manifest)[1] == 0
    key_a = make_key(root / "ka")
    assert key_a.installation_id != key_b.installation_id and key_a.key_id != key_b.key_id
    rejected = (
        "integrity_not_evaluated",
        "authenticity_invalid",
        "expectations_not_evaluated",
        "freshness_not_evaluated",
    )

    def observed(args, reason, status_states, exit_status=1):
        output, status = run(args)
        assert status == exit_status and reasons(output) == [reason], output
        assert states(output) == status_states and "verified_references" not in output
        assert output["notes"] == []

    # 1. B's key and fingerprint presented for installation A: authentic, expectations not met.
    observed(
        verify_args(b_set, key_b, manifest, installation=key_a.installation_id),
        "installation_mismatch",
        (
            "integrity_valid",
            "authenticity_valid",
            "expectations_not_met",
            "freshness_not_evaluated",
        ),
    )
    # 2. A's key and fingerprint with B's manifest: the key's binding differs from the declared
    #    installation (the corrected T25 row; see the docstring).
    observed(
        verify_args(b_set, key_a, manifest, installation=key_a.installation_id),
        "key_installation_mismatch",
        rejected,
    )
    # 3. B's key with A's fingerprint.
    args = verify_args(b_set, key_b, manifest)
    args[args.index("--expected-key-fingerprint") + 1] = key_a.fingerprint()
    observed(args, "key_fingerprint_mismatch", rejected)
    # Control for the code T25 lists: it is reachable only when the key carries the declared
    # installation binding but is a different key (a key reference mismatch), not across
    # installations.
    same_installation = make_key(root / "kc", installation_id=key_b.installation_id)
    observed(
        verify_args(b_set, same_installation, manifest),
        "manifest_key_reference_mismatch",
        rejected,
    )


def test_t26_attacker_recreates_manifest_and_set_without_the_key(world):
    attacker = make_key(world.root / "ka", installation_id=world.key.installation_id)
    attacker.key_id, attacker.created_at = world.key.key_id, world.key.created_at
    world.rewrite(lambda d: d["payload"]["body"].update(set_id=str(uuid.uuid4())), key=attacker)
    output, status = world.verify()
    assert status == 1 and reasons(output) == ["manifest_authentication_failed"]
    assert states(output) == (
        "integrity_not_evaluated",
        "authenticity_invalid",
        "expectations_not_evaluated",
        "freshness_not_evaluated",
    )


def test_t32_point_in_time_observation_is_not_a_guarantee(world):
    first, status = world.verify()
    assert status == 0 and first["point_in_time"] is True
    assert first["restore_performed"] is False and first["recovery_complete"] is False
    dump = world.synthetic.set_dir / "database.dump"
    data = bytearray(dump.read_bytes())
    data[0] ^= 1
    dump.write_bytes(bytes(data))  # modified after the successful verification
    second, status = world.verify()
    assert status == 1 and reasons(second) == ["set_member_hash_mismatch"]
    assert first["integrity"] == "integrity_valid"  # the first result stands as an observation


def run_cli(args, env=None):
    return subprocess.run(
        [sys.executable, "-I", "-m", "app.recovery_set", *args],
        capture_output=True,
        check=False,
        cwd=Path(verify_module.__file__).parents[2],
        env={"PATH": os.environ.get("PATH", ""), **(env or {})},
    )


def test_t33_key_material_never_appears(world, caplog):
    material = world.key.material
    forms = key_forms(material)
    scenarios = [verify_args(world.synthetic, world.key, world.manifest)]
    bad = list(scenarios[0])
    bad[bad.index("--expected-key-fingerprint") + 1] = "0" * 64
    scenarios.append(bad)
    leak_key = write_private(world.root / "k" / "leak.key", json.dumps({"material": material}))
    crashing = list(scenarios[0])
    crashing[crashing.index("--recovery-key") + 1] = str(leak_key)
    scenarios.append(crashing)
    for args in scenarios:
        done = run_cli(args)
        for form in forms:
            assert form not in done.stdout and form not in done.stderr
    assert all(form not in world.manifest.read_bytes() for form in forms)
    with caplog.at_level(logging.DEBUG):
        run(scenarios[0])
        run(scenarios[1])
    assert material not in caplog.text


def test_t33_t34_internal_errors_print_only_a_code(world, monkeypatch):
    material = world.key.material

    def boom(*args, **kwargs):
        raise RuntimeError(f"/secret/path {material} Traceback")

    monkeypatch.setattr(verify_module, "check_set", boom)
    output, status = world.verify()
    text = json.dumps(output)
    assert status == 1 and reasons(output) == ["internal_error"]
    assert material not in text and "/secret/path" not in text and "Traceback" not in text
    assert states(output)[:2] == ("integrity_not_evaluated", "authenticity_valid")
    check_closed(output)


def test_t34_output_allowlist_no_paths_or_exception_text(world):
    cases = []
    (world.synthetic.set_dir / "database.dump").write_bytes(b"x")
    cases.append(world.verify()[0])
    write_private(world.synthetic.set_dir / "weird\\u202e\\x07name", b"x")
    cases.append(world.verify()[0])
    world.key.path.chmod(0o644)
    cases.append(world.verify()[0])
    cases.append(run(["verify", "--set", str(world.root / "no" / "such")])[0])
    cases.append(run(["bogus", "--x", str(world.root)])[0])
    for output in cases:
        check_closed(output)
        text = json.dumps(output)
        for forbidden in (str(world.root), "Traceback", "weird", "/tmp", "Error", "errno"):
            assert forbidden not in text, forbidden


def test_t44_malformed_manifest_with_expected_hash(world):
    world.manifest.write_text("{bad")
    output, status = world.verify(extra=["--expected-manifest-hash", "a" * 64])
    assert status == 1 and states(output) == (
        "integrity_invalid",
        "authenticity_not_evaluated",
        "expectations_not_evaluated",
        "freshness_not_evaluated",
    )
    assert "manifest_hash" not in output


def test_t45_invalid_mac_with_matching_expected_hash(world):
    expected = world.hash()
    world.rewrite(lambda d: d.update(mac="0" * 64), resign=False)
    output, status = world.verify(extra=["--expected-manifest-hash", expected])
    assert status == 1 and reasons(output) == ["manifest_authentication_failed"]
    assert states(output) == (
        "integrity_not_evaluated",
        "authenticity_invalid",
        "expectations_not_evaluated",
        "freshness_not_evaluated",
    )
    assert "freshness_note" not in output and "manifest_hash" not in output


def test_t46_authentic_without_hash_is_not_a_failure(world):
    output, status = world.verify()
    assert status == 0 and output["freshness"] == "freshness_not_evaluated"


def test_t47_require_freshness_not_established(world):
    expected = world.hash()
    world.rewrite(lambda d: d.update(mac="0" * 64), resign=False)
    output, status = world.verify(
        extra=["--expected-manifest-hash", expected, "--require-freshness"]
    )
    assert status == 1
    assert reasons(output) == [
        "manifest_authentication_failed",
        "freshness_required_not_established",
    ]
    other = fresh(world, "m")
    other.manifest.write_text("{bad")
    output, status = other.verify(
        extra=["--expected-manifest-hash", "a" * 64, "--require-freshness"]
    )
    assert status == 1 and reasons(output) == [
        "manifest_malformed",
        "freshness_required_not_established",
    ]


def test_t48_archive_expectation_matrix(world, bare_world):
    out = bare_world.verify(expect="present")[0]
    assert (
        reasons(out) == ["archive_expectation_mismatch"]
        and states(out)[2] == "expectations_not_met"
    )
    out = world.verify(expect="absent")[0]
    assert reasons(out) == ["archive_expectation_mismatch"]
    removed = fresh(world, "gone")
    import shutil

    shutil.rmtree(removed.synthetic.set_dir / "archive")
    assert "set_member_missing" in reasons(removed.verify()[0])
    extra = build_world(world.root.parent / "extra", archive=False)
    private_dir(extra.synthetic.set_dir / "archive")
    assert reasons(extra.verify(expect="absent")[0]) == ["set_directory_unexpected"]


@pytest.mark.parametrize("operation", ["generate", "verify"])
def test_t48_expect_archive_is_mandatory_before_any_file_access(world, operation):
    if operation == "verify":
        args = verify_args(world.synthetic, world.key, world.manifest)
    else:
        from recovery_set_support import generate_args

        args = generate_args(world.synthetic, world.key, world.out_dir / "new")
    index = args.index("--expect-archive")
    del args[index : index + 2]
    output, status = run(args)
    assert status == 2 and reasons(output) == ["trust_input_missing"]
    assert states(output) == STATES
    assert not (world.out_dir / "new").exists()
    args += ["--expect-archive", "maybe"]
    assert reasons(run(args)[0]) == ["trust_input_malformed"]


@pytest.mark.parametrize(
    "flag",
    [
        "--set", "--manifest", "--recovery-key", "--expected-key-fingerprint",
        "--expected-installation-id", "--expected-schema-head",
    ],
)  # fmt: skip
def test_every_required_trust_input_is_mandatory(world, flag):
    args = verify_args(world.synthetic, world.key, world.manifest)
    index = args.index(flag)
    del args[index : index + 2]
    output, status = run(args)
    assert status == 2 and reasons(output) == ["trust_input_missing"] and states(output) == STATES


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--expected-key-fingerprint", "XYZ"),
        ("--expected-installation-id", "not-a-uuid"),
        ("--expected-schema-head", "bad rev!"),
    ],
)
def test_malformed_trust_inputs_fail_before_file_access(world, flag, value):
    args = verify_args(world.synthetic, world.key, world.manifest)
    args[args.index(flag) + 1] = value
    output, status = run(args)
    assert status == 2 and reasons(output) == ["trust_input_malformed"]


def test_trust_is_never_taken_from_the_manifest_or_environment(world, monkeypatch):
    monkeypatch.setenv("BUTLER_EXPECTED_INSTALLATION_ID", world.key.installation_id)
    args = verify_args(world.synthetic, world.key, world.manifest)
    index = args.index("--expected-installation-id")
    del args[index : index + 2]
    assert reasons(run(args)[0]) == ["trust_input_missing"]


def test_t53_verified_references_only_when_all_three_hold(world):
    output, _ = world.verify()
    refs = output["verified_references"]
    assert set(refs) == VERIFIED_KEYS and refs["manifest_hash"] == world.hash()
    assert len(refs["dump_sha256"]) == 64 and len(refs["members_digest"]) == 64
    failing = [
        world.verify(head=verifier_chain()[-2])[0],  # expectations not met
        world.verify(expect="absent")[0],
        run(["verify"])[0],
    ]
    other = fresh(world, "f")
    (other.synthetic.set_dir / "database.dump").write_bytes(b"changed")
    failing.append(other.verify()[0])
    bad_mac = fresh(world, "mac")
    bad_mac.rewrite(lambda d: d.update(mac="1" * 64), resign=False)
    failing.append(bad_mac.verify()[0])
    mismatch = world.verify(extra=["--expected-manifest-hash", "b" * 64])[0]
    assert "verified_references" in mismatch  # freshness mismatch fails the exit, not the three
    assert mismatch["freshness"] == "freshness_mismatch"
    for item in failing:
        assert "verified_references" not in item


def test_t54_expectations_are_reported_separately(world):
    output, status = world.verify(head=verifier_chain()[-2])
    assert status == 1
    assert states(output) == (
        "integrity_valid",
        "authenticity_valid",
        "expectations_not_met",
        "freshness_not_evaluated",
    )


def test_integrity_is_evaluated_even_when_expectations_fail(world):
    (world.synthetic.set_dir / "database.dump").write_bytes(b"changed")
    output = world.verify(head=verifier_chain()[-2])[0]
    assert "schema_head_mismatch" in reasons(output) and "set_member_size_mismatch" in reasons(
        output
    )
    assert states(output)[:3] == ("integrity_invalid", "authenticity_valid", "expectations_not_met")


def test_freshness_with_an_altered_file_follows_the_hash(world):
    (world.synthetic.set_dir / "database.dump").write_bytes(b"changed")
    output, _ = world.verify(extra=["--expected-manifest-hash", world.hash()])
    assert output["integrity"] == "integrity_invalid" and output["freshness"] == "freshness_match"


def test_manifest_hash_excludes_the_mac(world):
    before = world.hash()
    world.rewrite(lambda d: d.update(mac="0" * 64), resign=False)
    assert world.hash() == before


def test_a2_every_output_uses_the_closed_vocabulary(world, bare_world):
    outputs = [
        world.verify()[0],
        bare_world.verify()[0],
        world.verify(extra=["--expected-manifest-hash", world.hash()])[0],
        world.verify(expect="absent")[0],
    ]
    for output in outputs:
        check_closed(output)


def pin_locale(monkeypatch, value):
    """Set the locale environment before a guarded call (gettext reads it on every lookup)."""
    for name in ("LANGUAGE", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LC_ALL", value)


def missing_generate_input_args(world, flag):
    from recovery_set_support import generate_args

    args = generate_args(world.synthetic, world.key, world.out_dir / "new-manifest")
    index = args.index(flag)
    del args[index : index + 2]
    return args


LOCALE_ENVIRONMENTS = {
    "inherited": None,  # the environment of the process, unchanged (CI sets C.UTF-8)
    "C": {"LC_ALL": "C"},
    "C.UTF-8": {"LC_ALL": "C.UTF-8"},
    "LANGUAGE-override": {"LANGUAGE": "de:fr", "LANG": "en_US.UTF-8"},
    "LC_MESSAGES-override": {"LC_MESSAGES": "ja_JP.UTF-8", "LANG": "C.UTF-8"},
}


def set_locale_environment(monkeypatch, name):
    """Vary the locale environment of the test process (production never does this).

    No translated catalog is assumed to exist: the result must not depend on that.
    """
    values = LOCALE_ENVIRONMENTS[name]
    if values is None:
        return
    for variable in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(variable, raising=False)
    for variable, value in values.items():
        monkeypatch.setenv(variable, value)


GENERATE_REQUIRED = (
    "--set", "--recovery-key", "--expected-key-fingerprint", "--expect-archive",
    "--output", "--installation-id", "--schema-head",
)  # fmt: skip
VERIFY_REQUIRED = (
    "--set", "--recovery-key", "--expected-key-fingerprint", "--expect-archive",
    "--manifest", "--expected-installation-id", "--expected-schema-head",
)  # fmt: skip


def a5_arguments(world, operation):
    from recovery_set_support import generate_args

    if operation == "generate":
        return generate_args(world.synthetic, world.key, world.out_dir / "new-manifest")
    return verify_args(world.synthetic, world.key, world.manifest)


def assert_rejected_before_any_file_access(world, args, operation, reason, status=2):
    """Run ``args`` under strict zero-access guards, installed after fixture setup, and check the
    closed result, that nothing was published and that the output directory is unchanged."""
    listing = sorted(path.name for path in world.out_dir.iterdir())  # holds the fixture manifest
    with file_access_guards(raising=False) as (counts, _, calls):
        output, code = run(args)
    assert dict(counts) == {}, (dict(counts), describe_calls(calls))
    assert code == status and reasons(output) == [reason], output
    if args[:1] == ["generate"]:  # an unrecognised operation reports as the default, verify
        assert output["publication"] == "not_published"
    assert not (world.out_dir / "new-manifest").exists()
    assert sorted(path.name for path in world.out_dir.iterdir()) == listing


@pytest.mark.parametrize("locale_name", sorted(LOCALE_ENVIRONMENTS))
@pytest.mark.parametrize(
    ("operation", "flag"),
    [("generate", flag) for flag in GENERATE_REQUIRED]
    + [("verify", flag) for flag in VERIFY_REQUIRED],
)
def test_a5_every_required_input_is_mandatory_before_any_file_access(
    world, monkeypatch, operation, flag, locale_name
):
    """A5: a missing required input is rejected with zero guarded filesystem calls, whatever
    the locale environment. No tolerated call, count or path; the locale is not pinned."""
    args = a5_arguments(world, operation)
    index = args.index(flag)
    del args[index : index + 2]
    set_locale_environment(monkeypatch, locale_name)
    assert_rejected_before_any_file_access(world, args, operation, "trust_input_missing")


def replaced(args, flag, value):
    args = list(args)
    args[args.index(flag) + 1] = value
    return args


GENERATE_MALFORMED = [
    ("--installation-id", "not-a-uuid"),
    ("--schema-head", "bad rev!"),
    ("--expected-key-fingerprint", "XYZ"),
    ("--expect-archive", "maybe"),
]
VERIFY_MALFORMED = [
    ("--expected-installation-id", "not-a-uuid"),
    ("--expected-schema-head", "bad rev!"),
    ("--expected-key-fingerprint", "XYZ"),
    ("--expect-archive", "maybe"),
]


def malformed_cases():
    cases = []
    for flag, value in GENERATE_MALFORMED:
        cases.append(("generate", f"{flag}={value}", lambda a, f=flag, v=value: replaced(a, f, v)))
    for flag, value in VERIFY_MALFORMED:
        cases.append(("verify", f"{flag}={value}", lambda a, f=flag, v=value: replaced(a, f, v)))
    optional = [
        ("generate", "--model-digest", "zz"),
        ("generate", "--model-tag", "no tag"),
        ("generate", "--work-suppression-manifest-sha256", "abc"),
        ("generate", "--work-source-checkpoint-sha256", "ABC"),
        ("verify", "--expected-manifest-hash", "abc"),
    ]
    for operation, flag, value in optional:
        cases.append((operation, f"{flag}={value}", lambda a, f=flag, v=value: [*a, f, v]))
    cases += [
        ("generate", "tag-without-digest", lambda a: [*a, "--model-tag", "model:1"]),
        ("generate", "digest-without-tag", lambda a: [*a, "--model-digest", "a" * 64]),
        # Parser errors.
        ("generate", "unknown-option", lambda a: [*a, "--limit", "1"]),
        ("verify", "unknown-option", lambda a: [*a, "--fault", "1"]),
        ("verify", "generate-only-option", lambda a: [*a, "--output", "x"]),
        ("generate", "verify-only-option", lambda a: [*a, "--manifest", "x"]),
        ("generate", "ambiguous-abbreviation", lambda a: [*a, "--s", "x"]),
        ("generate", "missing-value-at-end", lambda a: [*a, "--model-tag"]),
        ("generate", "value-looks-like-option", lambda a: [*a, "--model-tag", "--set"]),
        ("generate", "stray-positional", lambda a: [*a, "stray"]),
        ("generate", "double-dash", lambda a: [*a, "--", "x"]),
        ("verify", "flag-with-explicit-value", lambda a: [*a, "--require-freshness=yes"]),
        ("verify", "unknown-single-dash", lambda a: [*a, "-x"]),
        ("generate", "option-before-operation", lambda a: [a[1], a[2], a[0], *a[3:]]),
        ("generate", "unknown-operation", lambda a: ["restore", *a[1:]]),
        ("generate", "no-operation", lambda a: []),
    ]
    return cases


@pytest.mark.parametrize("locale_name", sorted(LOCALE_ENVIRONMENTS))
@pytest.mark.parametrize(
    ("operation", "label", "mutate"),
    malformed_cases(),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_a5_malformed_input_and_parser_errors_are_rejected_before_any_file_access(
    world, monkeypatch, operation, label, mutate, locale_name
):
    """A5 for the shapes that are present but wrong, including every parser error path."""
    args = mutate(a5_arguments(world, operation))
    set_locale_environment(monkeypatch, locale_name)
    assert_rejected_before_any_file_access(world, args, operation, "trust_input_malformed")


@pytest.mark.parametrize("locale_name", sorted(LOCALE_ENVIRONMENTS))
def test_t20_freshness_requested_without_a_hash_is_rejected_before_any_file_access(
    world, monkeypatch, locale_name
):
    args = [*a5_arguments(world, "verify"), "--require-freshness"]
    set_locale_environment(monkeypatch, locale_name)
    assert_rejected_before_any_file_access(
        world, args, "verify", "freshness_requested_without_expected_hash"
    )


def test_a5_the_guard_observes_the_gettext_lookup_that_argparse_makes_under_a_non_c_locale(
    monkeypatch,
):
    """Sensitivity control for the zero-call results above: under ``LC_ALL=C.UTF-8`` merely
    constructing an ``argparse`` parser (what the CLI did before) includes guarded ``os.stat``
    calls of ``.../LC_MESSAGES/messages.mo`` paths made inside ``gettext.find``. The same guard
    therefore can see the lookup that caused the hosted-CI failures; it does not assume a catalog
    exists.
    """
    import argparse

    set_locale_environment(monkeypatch, "C.UTF-8")
    with file_access_guards(raising=False) as (_, _, calls):
        argparse.ArgumentParser(prog="control")
    lookups = [
        frames
        for kind, path, frames in calls
        if kind == "os.stat" and path and path.endswith("/LC_MESSAGES/messages.mo")
    ]
    assert lookups, "expected gettext to look for a catalog under a non-C locale"
    # Other calls may be recorded (coverage's own tracing stats files the first time it sees
    # one); only the catalog stats are claimed here, and each is made inside gettext.find.
    for frames in lookups:
        assert any(name.endswith("gettext.py") and func == "find" for name, func, _ in frames)


def reference_parse(argv):
    """The parser the CLI used before the A5 correction (``argparse``), kept here as an oracle."""
    import argparse

    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise ValueError("malformed")

        def exit(self, status=0, message=None):
            raise ValueError("malformed")

    parser = Parser(prog="recovery_set", add_help=False)
    commands = parser.add_subparsers(dest="operation", parser_class=Parser)
    for operation, names in (("generate", GENERATE_OPTIONS_REF), ("verify", VERIFY_OPTIONS_REF)):
        command = commands.add_parser(operation, add_help=False)
        for name in names:
            command.add_argument(f"--{name}", default=None)
        if operation == "verify":
            command.add_argument("--require-freshness", action="store_true", default=False)
    args = parser.parse_args(argv)
    if args.operation is None:
        raise ValueError("malformed")
    return vars(args)


GENERATE_OPTIONS_REF = (
    "set", "recovery-key", "expected-key-fingerprint", "expect-archive", "output",
    "installation-id", "schema-head", "model-tag", "model-digest",
    "work-suppression-manifest-sha256", "work-source-checkpoint-sha256",
)  # fmt: skip
VERIFY_OPTIONS_REF = (
    "set", "recovery-key", "expected-key-fingerprint", "expect-archive", "manifest",
    "expected-installation-id", "expected-schema-head", "expected-manifest-hash",
)  # fmt: skip


def new_parse(argv):
    from app.recovery_set.cli import parse_arguments

    try:
        return vars(parse_arguments(argv))
    except CodedError:
        raise ValueError("malformed") from None


def test_the_closed_parser_agrees_with_the_argparse_parser_it_replaced():
    """Same accepted values and same malformed outcomes over a fixed and a seeded random corpus
    (``--`` is the one documented narrowing: the closed parser always rejects it)."""
    import random

    pool = [
        "generate", "verify", "--set", "--recovery-key", "--output", "--manifest", "--installation-id",
        "--expect-archive", "--require-freshness", "--model-tag", "--model-digest", "--s", "--se",
        "--expected", "--expected-m", "--expect", "--limit", "--set=a", "--set=", "--output=b",
        "--require-freshness=1", "-x", "-", "-5", "-1.5", "-a b", "a", "b c", "", "present",
        "absent", "--set=--output", "--sch", "--schema-head=head", "stray",
    ]  # fmt: skip
    rng = random.Random(7405)
    corpus = [[], ["generate"], ["verify"], ["restore"], ["--set", "a", "generate"]]
    corpus += [
        [
            rng.choice(("generate", "verify")),
            *[rng.choice(pool[2:]) for _ in range(rng.randint(0, 6))],
        ]
        for _ in range(4000)
    ]
    disagreements = []
    accepted = 0
    for argv in corpus:
        try:
            expected = reference_parse(argv)
        except ValueError:
            expected = None
        try:
            actual = new_parse(argv)
        except ValueError:
            actual = None
        if expected is None or actual is None:
            if (expected is None) != (actual is None):
                disagreements.append((argv, expected, actual))
            continue
        accepted += 1
        mine = {key: actual[key] for key in expected}
        extras = {key: value for key, value in actual.items() if key not in expected}
        if mine != expected or any(value not in (None, False) for value in extras.values()):
            disagreements.append((argv, expected, actual))
    assert accepted > 200  # the corpus is not trivially all-rejected
    assert not disagreements, disagreements[:5]
    for argv in (
        ["generate", "--", "--set", "a"],
        ["verify", "--set", "a", "--"],
        ["generate", "--"],
    ):
        with pytest.raises(ValueError):
            new_parse(argv)


def test_a2_authentic_altered_file_reports_freshness_per_supplied_hash(world):
    """Section 2.5 row "Authentic, one file altered": freshness follows the supplied hash."""
    expected = world.hash()
    dump = world.synthetic.set_dir / "database.dump"
    dump.write_bytes(dump.read_bytes()[:-1] + b"X")
    cases = [
        ([], "freshness_not_evaluated"),
        (["--expected-manifest-hash", expected], "freshness_match"),
        (["--expected-manifest-hash", "b" * 64], "freshness_mismatch"),
    ]
    for extra, freshness in cases:
        output, status = world.verify(extra=extra)
        check_closed(output)
        assert status == 1 and output["freshness"] == freshness, extra
        assert states(output)[:3] == ("integrity_invalid", "authenticity_valid", "expectations_met")
        assert "set_member_hash_mismatch" in reasons(output)
        assert "verified_references" not in output


def test_t33_key_material_is_absent_from_generate_output_and_files(world):
    """T33 for ``generate`` through the real CLI boundary (subprocess).

    Scans stdout, stderr and the files the run wrote. The key files read by the runs are test
    fixtures (inputs), not generated outputs, and sit outside the scanned output directory.
    The second scenario is an ordinary validation failure (a malformed key file), not an injected
    internal error.
    """
    from recovery_set_support import generate_args

    forms = key_forms(world.key.material)
    leak_key = write_private(
        world.root / "k" / "leak2.key", json.dumps({"material": world.key.material})
    )
    assert world.out_dir not in world.key.path.parents and world.out_dir not in leak_key.parents
    valid = generate_args(world.synthetic, world.key, world.out_dir / "generated")
    malformed = generate_args(world.synthetic, world.key, world.out_dir / "crashing")
    malformed[malformed.index("--recovery-key") + 1] = str(leak_key)
    control = run_cli(valid)
    assert control.returncode == 0 and json.loads(control.stdout)["reasons"] == []
    rejected = run_cli(malformed)
    assert rejected.returncode == 1
    assert json.loads(rejected.stdout)["reasons"] == ["key_namespace_mismatch"]
    for done in (control, rejected):
        for form in forms:
            assert form not in done.stdout and form not in done.stderr
    written = [path for path in world.out_dir.iterdir() if path.is_file()]
    assert (world.out_dir / "generated").exists() and not (world.out_dir / "crashing").exists()
    assert {path.name for path in written} >= {"generated"}
    for path in written:
        assert all(form not in path.read_bytes() for form in forms), path.name


def test_t33_application_logs_never_contain_key_material(world, caplog):
    """T33 "logs": in-process ``generate`` and ``verify`` runs with application logs captured.

    This is separate from the subprocess checks above (they cover the real CLI output boundary).
    The tool itself defines no logger, so the capture is a negative check of the logging module's
    output for these scenarios; a control record proves the capture is wired.
    """
    from recovery_set_support import generate_args

    material = world.key.material
    forms = [form.decode("latin-1") for form in key_forms(material)]
    leak_key = write_private(world.root / "k" / "leak3.key", json.dumps({"material": material}))
    wrong = verify_args(world.synthetic, world.key, world.manifest)
    wrong[wrong.index("--expected-key-fingerprint") + 1] = "0" * 64
    bad_verify = verify_args(world.synthetic, world.key, world.manifest)
    bad_verify[bad_verify.index("--recovery-key") + 1] = str(leak_key)
    bad_generate = generate_args(world.synthetic, world.key, world.out_dir / "log-bad")
    bad_generate[bad_generate.index("--recovery-key") + 1] = str(leak_key)
    scenarios = [
        (
            "generate valid",
            generate_args(world.synthetic, world.key, world.out_dir / "log-ok"),
            0,
            [],
        ),
        ("generate malformed key", bad_generate, 1, ["key_namespace_mismatch"]),
        ("verify valid", verify_args(world.synthetic, world.key, world.manifest), 0, []),
        ("verify wrong fingerprint", wrong, 1, ["key_fingerprint_mismatch"]),
        ("verify malformed key", bad_verify, 1, ["key_namespace_mismatch"]),
    ]
    with caplog.at_level(logging.DEBUG):
        for label, args, status, expected in scenarios:
            output, code = run(args)
            assert (code, output["reasons"]) == (status, expected), label
        logging.getLogger("app.recovery_set").debug("capture-control")
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "capture-control" in messages  # the capture is wired
    for form in forms:
        assert form not in caplog.text and form not in messages


def test_file_access_guards_observe_the_entry_points_a_real_generate_uses(world):
    from recovery_set_support import generate_args

    args = generate_args(world.synthetic, world.key, world.out_dir / "observed")
    with file_access_guards(raising=False) as (counts, origins, _):
        output, status = run(args)
    assert status == 0 and output["reasons"] == []
    for kind in ("os.open", "os.lstat", "os.stat", "os.scandir", "os.fstat", "os.read"):
        assert counts[kind] > 0 and origins[kind] > 0, (kind, dict(counts), dict(origins))


def test_file_access_guards_refuse_a_real_access_and_record_it(world):
    from recovery_set_support import generate_args

    target = world.out_dir / "refused"
    args = generate_args(world.synthetic, world.key, target)  # built before the guards exist
    with file_access_guards(raising=True) as (counts, origins, _):
        output, status = run(args)
    assert output["reasons"] == ["internal_error"] and status == 1  # the guard fired
    assert sum(counts.values()) > 0 and sum(origins.values()) > 0
    assert not target.exists()
