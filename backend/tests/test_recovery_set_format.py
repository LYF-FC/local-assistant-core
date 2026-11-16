# ruff: noqa: F811
"""Spec 074 B010 to B013: format, canonical JSON, key model, domains (T8 to T16, T24)."""

import json
import os
import uuid

import pytest
from recovery_set_support import (  # noqa: F401
    CREATED,
    World,
    bare_world,
    build_world,
    describe_calls,
    file_access_guards,
    make_key,
    private_dir,
    run_generate,
    run_verify,
    world,
    write_private,
)

from app.recovery_set.cli import run
from app.recovery_set.format import (
    FINGERPRINT_DOMAIN,
    HASH_DOMAIN,
    MAC_DOMAIN,
    CodedError,
    Limits,
    canonical,
    parse_manifest,
)
from app.recovery_set.key import KeyFile, load_key

LIMITS = Limits()


def reasons(output):
    return output["reasons"]


def test_valid_manifest_roundtrips_and_is_canonical(world):
    data = world.manifest.read_bytes()
    envelope, _ = parse_manifest(data)
    assert canonical(json.loads(data)) == data and not data.endswith(b"\n")
    assert envelope.payload.body.members[0].path == "archive/.archive.json"


def test_domains_are_distinct_and_separate_from_work_domains():
    domains = {MAC_DOMAIN, FINGERPRINT_DOMAIN, HASH_DOMAIN}
    assert len(domains) == 3
    for domain in domains:
        assert b"work" not in domain and b"synthetic" not in domain


def test_t8_duplicate_key_top_level_and_nested(world):
    text = world.manifest.read_text()
    top = text.replace(
        '"algorithm":"HMAC-SHA256"', '"algorithm":"HMAC-SHA256","algorithm":"HMAC-SHA256"'
    )
    nested = text.replace('"installation_id":', '"installation_id":"x","installation_id":', 1)
    for bad in (top, nested):
        world.manifest.write_text(bad)
        assert reasons(world.verify()[0]) == ["manifest_duplicate_key"]


def test_t9_unknown_field_at_every_depth(world):
    def top(d):
        d["extra"] = 1

    def payload(d):
        d["payload"]["extra"] = 1

    def body(d):
        d["payload"]["body"]["extra"] = 1

    def nested(d):
        d["payload"]["body"]["installation"]["extra"] = 1

    def member(d):
        d["payload"]["body"]["members"][0]["extra"] = 1

    def model(d):
        d["payload"]["body"]["model"]["extra"] = 1

    for mutate in (top, payload, body, nested, member, model):
        fresh = build_world(world.root.parent / uuid.uuid4().hex)
        fresh.rewrite(mutate)
        assert reasons(fresh.verify()[0]) == ["manifest_unknown_field"], mutate.__name__


def test_t10_malformed_and_noncanonical(world):
    world.manifest.write_text("{not json")
    assert reasons(world.verify()[0]) == ["manifest_malformed"]
    for number, raw in enumerate(
        (
            lambda d: json.dumps(d, sort_keys=True).encode(),  # whitespace
            lambda d: json.dumps(dict(reversed(list(d.items()))), separators=(",", ":")).encode(),
            lambda d: canonical(d).replace(b"archive/", b"archive\\/", 1),  # escape variant
        )
    ):
        fresh = build_world(world.root.parent / f"n{number}")
        fresh.rewrite(lambda d: None, raw=raw)
        out = fresh.verify()[0]
        assert out["integrity"] == "integrity_invalid"
        assert reasons(out) == ["manifest_noncanonical"], number
        assert out["authenticity"] == "authenticity_not_evaluated"
    fresh = build_world(world.root.parent / "trailing")
    fresh.rewrite(lambda d: None, raw=lambda d: canonical(d) + b"\n")
    assert reasons(fresh.verify()[0]) == ["manifest_noncanonical"]


def test_floats_nan_and_wrong_types_are_rejected(world):
    text = world.manifest.read_text()
    for bad in (
        text.replace('"size":20', '"size":20.0', 1),
        text.replace('"schema_version":1', '"schema_version":NaN'),
    ):
        world.manifest.write_text(bad)
        assert reasons(world.verify()[0])[0] in {
            "manifest_malformed",
            "manifest_schema_unsupported",
        }


def test_t11_schema_version_and_purpose(world):
    for mutate in (
        lambda d: d.update(schema_version=2),
        lambda d: d.update(schema_version=True),
        lambda d: d.update(schema_version="1"),
        lambda d: d.pop("schema_version"),
        lambda d: d.update(purpose="butler.other.v1"),
    ):
        fresh = build_world(world.root.parent / uuid.uuid4().hex)
        fresh.rewrite(mutate)
        assert reasons(fresh.verify()[0]) == ["manifest_schema_unsupported"]


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd", "../x", "archive/../x", "archive\\x", "archive/\x00x", "archive//x",
        "archive/" + "a" * 70, "Database.dump", "archive/.ARCHIVE.json", "database.dump/",
        "archive/аbc.original", "archive/" + "A" * 32 + "-v1.original",
    ],
)  # fmt: skip
def test_t7_manifest_path_unsafe(world, path):
    world.rewrite(lambda d: d["payload"]["body"]["members"][0].update(path=path))
    out = world.verify()[0]
    assert reasons(out) == ["manifest_path_unsafe"] and out["integrity"] == "integrity_invalid"


T7_MARKER = "T7-OUTSIDE-SENTINEL"


def make_outside_sentinel(world):
    """Synthetic content next to the set that no member path may ever lead to."""
    directory = world.root / f"{T7_MARKER}-dir"
    directory.mkdir()
    sentinel = directory / f"{T7_MARKER}.txt"
    sentinel.write_bytes(b"synthetic outside sentinel: never to be read, listed or changed\n")
    return directory, sentinel


def t7_member_paths(world, sentinel):
    """Unsafe member-path spellings, most of them aimed at the outside sentinel."""
    relative = os.path.relpath(sentinel, world.synthetic.set_dir)
    return {
        "relative-traversal": relative,
        "absolute": str(sentinel),
        "traversal-through-archive": "archive/" + relative,
        "backslash-traversal": relative.replace("/", "\\"),
        "nul-in-segment": "archive/\x00" + sentinel.name,
        "empty-segment": "archive//" + relative,
        "over-length-segment": "archive/" + "a" * 70,
        "unicode-look-alike": "archive/аbc.original",
        "case-variant-of-dump": "Database.dump",
    }


def snapshot(*paths):
    state = {}
    for path in paths:
        info = path.stat()
        state[path.name] = (
            path.read_bytes() if path.is_file() else sorted(item.name for item in path.iterdir()),
            info.st_mode,
            info.st_ino,
            info.st_size,
            info.st_mtime_ns,
            info.st_nlink,
        )
    return state


def escape_attempts(calls, world):
    """Guarded calls whose path argument could reach beyond the set.

    A call is an attempt when its path names the outside sentinel or its directory, has a ``..``
    segment, a backslash or a NUL, or is absolute and neither inside nor an ancestor of one of
    the independently supplied locations: the set, the key file, the manifest and the output
    directory. Descriptor walks of the supplied paths' ancestors and the set's own member names
    are therefore not attempts; a path outside those is.
    """
    supplied = [
        os.path.normpath(str(item))
        for item in (world.synthetic.set_dir, world.key.path, world.manifest, world.out_dir)
    ]
    found = []
    for kind, path, _ in calls:
        if path is None:
            continue
        segments = path.split("/")
        reasons = []
        if T7_MARKER in path:
            reasons.append("names the outside sentinel")
        if ".." in segments or "\\" in path or "\x00" in path:
            reasons.append("traversal, backslash or NUL")
        if os.path.isabs(path):
            target = os.path.normpath(path)
            related = any(
                target == root
                or target.startswith(root + os.sep)
                or root.startswith(target.rstrip(os.sep) + os.sep)
                for root in supplied
            )
            if not related:
                reasons.append("absolute path outside the supplied locations")
        if reasons:
            found.append((kind, path, reasons))
    # Report member-path escapes (sentinel, traversal) before incidental absolute paths.
    return sorted(
        found, key=lambda item: item[2] == ["absolute path outside the supplied locations"]
    )


@pytest.mark.parametrize(
    "variant",
    [
        "relative-traversal", "absolute", "traversal-through-archive", "backslash-traversal",
        "nul-in-segment", "empty-segment", "over-length-segment", "unicode-look-alike",
        "case-variant-of-dump",
    ],
)  # fmt: skip
def test_t7_unsafe_member_paths_cannot_reach_outside_the_set(world, variant):
    """T7: the manifest names a member path aimed at (or shaped like) something outside the set.

    The run is rejected with ``manifest_path_unsafe``; while it runs, no guarded filesystem call
    names the outside sentinel, climbs out with ``..``, uses a backslash or NUL, or addresses an
    absolute path outside the independently supplied key, manifest, set and output locations; the
    sentinel and its directory, the set and the manifest are unchanged. The key and manifest
    reads, and their ancestor walks, are legitimate and are observed (the guard is live).
    """
    from recovery_set_support import verify_args

    directory, sentinel = make_outside_sentinel(world)
    member_path = t7_member_paths(world, sentinel)[variant]
    world.rewrite(lambda d: d["payload"]["body"]["members"][0].update(path=member_path))
    args = verify_args(world.synthetic, world.key, world.manifest)  # built before the guards
    watched = (sentinel, directory, world.synthetic.set_dir, world.manifest)
    before = snapshot(*watched)
    with file_access_guards(raising=False) as (counts, _, calls):
        output, status = run(args)
    assert not escape_attempts(calls, world), escape_attempts(calls, world)
    assert snapshot(*watched) == before
    assert counts["os.open"] > 0 and counts["os.read"] > 0  # the legitimate reads are seen
    assert any(path and path.endswith(world.manifest.name) for _, path, _ in calls)
    assert status == 1 and reasons(output) == ["manifest_path_unsafe"], output
    assert output["integrity"] == "integrity_invalid"


def test_t7_the_escape_guard_detects_an_attempted_escape(world):
    """Controls for the T7 test: a real read of the sentinel is flagged, the path a naive
    implementation would open for each targeted member-path spelling is flagged, and a refusing
    guard stops the access itself, leaving the sentinel untouched."""
    directory, sentinel = make_outside_sentinel(world)
    with file_access_guards(raising=False) as (_, _, calls):
        assert b"synthetic outside sentinel" in sentinel.read_bytes()
    flagged = escape_attempts(calls, world)
    assert flagged and all("names the outside sentinel" in why for _, _, why in flagged)
    paths = t7_member_paths(world, sentinel)
    targeted = (
        "relative-traversal", "absolute", "traversal-through-archive",
        "backslash-traversal", "nul-in-segment", "empty-segment",
    )  # fmt: skip
    for variant in targeted:
        naive = os.path.join(world.synthetic.set_dir, paths[variant])
        with file_access_guards(raising=False) as (_, _, calls):
            try:  # what an implementation that trusted the member path would do
                os.close(os.open(naive, os.O_RDONLY))
            except (OSError, ValueError):
                pass
        assert escape_attempts(calls, world), variant
    before = snapshot(sentinel, directory)
    with (
        file_access_guards(raising=True) as (_, _, calls),
        pytest.raises(Exception, match="os.open"),
    ):
        os.open(sentinel, os.O_RDONLY)
    assert snapshot(sentinel, directory) == before
    assert escape_attempts(calls, world)


def test_t7_duplicate_member_paths_are_ambiguous(world):
    world.rewrite(
        lambda d: d["payload"]["body"]["members"].append(dict(d["payload"]["body"]["members"][-1]))
    )
    assert reasons(world.verify()[0]) == ["set_enumeration_ambiguous"]


def test_t12_oversized_manifest_and_key(world):
    world.manifest.write_bytes(b" " * (4 * 1024 * 1024 + 1))
    assert reasons(world.verify()[0]) == ["manifest_too_large"]
    fresh = build_world(world.root.parent / "key")
    fresh.key.path = write_private(fresh.root / "k" / "big.key", b"x" * 2049)
    assert reasons(fresh.verify()[0]) == ["key_file_unsafe"]
    # the bounds themselves are existing-code-derived or provisional, and never a capacity claim
    assert (Limits().key_file_bytes, Limits().manifest_bytes) == (2048, 4 * 1024 * 1024)


def test_t13_key_file_problems(world):
    key = world.key
    original = key.path
    # missing
    original.rename(original.with_name("moved"))
    out = world.verify()[0]
    assert reasons(out) == ["key_file_unsafe"] and out["authenticity"] == "authenticity_invalid"
    original.with_name("moved").rename(original)
    # any group or other bit, including read-only bits
    for mode in (0o640, 0o604, 0o620, 0o602, 0o660, 0o666):
        original.chmod(mode)
        assert reasons(world.verify()[0]) == ["key_file_unsafe"], oct(mode)
    original.chmod(0o600)
    # symlink
    link = original.with_name("link.key")
    link.symlink_to(original)
    key.path = link
    assert reasons(world.verify()[0]) == ["key_file_unsafe"]
    # hard-linked key
    key.path = original
    os.link(original, original.with_name("alias.key"))
    assert reasons(world.verify()[0]) == ["key_file_unsafe"]


def test_t14_incorrect_key_with_its_own_fingerprint(world):
    other = make_key(world.root / "k2", installation_id=world.key.installation_id)
    result = run_verify(world.synthetic, other, world.manifest)[0]
    assert reasons(result)[0] in {
        "manifest_key_reference_mismatch",
        "manifest_authentication_failed",
    }
    assert result["authenticity"] == "authenticity_invalid"
    # same key id and public fields, different material: the keyed fingerprint differs
    forged = make_key(world.root / "k3", installation_id=world.key.installation_id)
    forged.key_id, forged.created_at = world.key.key_id, world.key.created_at
    write_private(forged.path, json.dumps(forged.document()))
    assert forged.fingerprint() != world.key.fingerprint()
    assert reasons(run_verify(world.synthetic, forged, world.manifest)[0]) == [
        "manifest_key_reference_mismatch"
    ]


def test_t15_correct_key_wrong_expected_fingerprint(world):
    from recovery_set_support import verify_args

    from app.recovery_set.cli import run

    base = verify_args(world.synthetic, world.key, world.manifest)
    base[base.index("--expected-key-fingerprint") + 1] = "0" * 64
    out = run(base)[0]
    assert reasons(out) == ["key_fingerprint_mismatch"]


def test_t16_work_key_file_is_a_wrong_namespace(world):
    work = {
        "schema_version": 1,
        "mode": "synthetic_work_suppression_key",
        "key_id": str(uuid.uuid4()),
        "workspace_id": str(uuid.uuid4()),
        "created_at": "2026-11-14T00:00:00+00:00",
        "material": "ab" * 32,
    }
    path = write_private(world.root / "k" / "work.key", json.dumps(work))
    world.key.path = path
    assert reasons(world.verify()[0]) == ["key_namespace_mismatch"]
    # a database-credential-like file with another purpose
    other = {**world.key.document(), "purpose": "database_credential"}
    world.key.path = write_private(world.root / "k" / "db.key", json.dumps(other))
    assert reasons(world.verify()[0]) == ["key_namespace_mismatch"]


def test_malformed_key_file(world):
    for text in (
        "[]",
        "{",
        json.dumps({**world.key.document(), "material": "zz"}),
        json.dumps({**world.key.document(), "extra": 1}),
    ):
        world.key.path = write_private(world.root / "k" / "bad.key", text)
        assert reasons(world.verify()[0]) == ["key_file_malformed"]


def test_t24_key_rotation(tmp_path):
    first = build_world(tmp_path / "a")
    second = make_key(tmp_path / "a" / "k2", installation_id=first.key.installation_id)
    # K1 manifest verified with K2 and fingerprint(K2)
    assert reasons(run_verify(first.synthetic, second, first.manifest)[0])[0] in {
        "manifest_key_reference_mismatch",
        "manifest_authentication_failed",
    }
    # K1 key file with fingerprint(K2)
    from recovery_set_support import verify_args

    from app.recovery_set.cli import run

    args = verify_args(first.synthetic, first.key, first.manifest)
    args[args.index("--expected-key-fingerprint") + 1] = second.fingerprint()
    assert reasons(run(args)[0]) == ["key_fingerprint_mismatch"]
    # K1 with fingerprint(K1)
    assert first.verify()[1] == 0


def test_key_material_is_masked_in_repr_and_model(world):
    key = load_key(world.key.path, LIMITS)
    assert world.key.material not in repr(key) and world.key.material not in str(key)
    assert world.key.material not in repr(key.model_dump())
    assert isinstance(key, KeyFile)


def test_fingerprint_is_keyed_not_an_unkeyed_hash(world):
    import hashlib

    key = load_key(world.key.path, LIMITS)
    unkeyed = hashlib.sha256(FINGERPRINT_DOMAIN + canonical(key.public_identity())).hexdigest()
    assert key.fingerprint() != unkeyed
    assert CREATED == key.created_at


def test_parse_manifest_error_type_is_a_closed_code():
    with pytest.raises(CodedError) as caught:
        parse_manifest(b"{}")
    assert caught.value.code == "manifest_schema_unsupported"
    with pytest.raises(ValueError):
        CodedError("not_a_reason_code")


def test_unused_helpers_exist():
    assert callable(run_generate) and callable(private_dir) and World and isinstance(LIMITS, Limits)


def test_mac_fingerprint_and_hash_use_their_own_domains(world):
    """Golden recomputation: dropping or swapping a domain prefix must be detected."""
    import hashlib
    import hmac

    key = load_key(world.key.path, LIMITS)
    secret = bytes.fromhex(world.key.material)
    document = world.load()
    payload = canonical(document["payload"])
    assert document["mac"] == hmac.new(secret, MAC_DOMAIN + payload, hashlib.sha256).hexdigest()
    assert document["mac"] != hmac.new(secret, payload, hashlib.sha256).hexdigest()
    identity = canonical(key.public_identity())
    expected = hmac.new(secret, FINGERPRINT_DOMAIN + identity, hashlib.sha256).hexdigest()
    assert key.fingerprint() == expected == document["payload"]["key_fingerprint"]
    assert world.hash() == hashlib.sha256(HASH_DOMAIN + payload).hexdigest()
    assert world.hash() != hashlib.sha256(payload).hexdigest()


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read a mode 000 file")
def test_t13_unreadable_key_file_is_unsafe(world):  # pragma: no cover - needs a non-root user
    world.key.path.chmod(0o000)
    try:
        out = world.verify()[0]
    finally:
        world.key.path.chmod(0o600)
    assert reasons(out) == ["key_file_unsafe"] and out["authenticity"] == "authenticity_invalid"


@pytest.mark.parametrize(
    "path",
    [
        ("application",),
        ("application", "packages"),
        ("archive",),
        ("generator",),
        ("schema",),
        ("work_references",),
    ],
)
def test_t9_unknown_field_in_every_remaining_nested_object(world, path):
    """T9 "at every depth": the closed objects not covered by the test above."""

    def mutate(document):
        node = document["payload"]["body"]
        for name in path:
            node = node[name]
        node["extra"] = 1

    fresh = build_world(world.root.parent / uuid.uuid4().hex)
    fresh.rewrite(mutate)
    assert reasons(fresh.verify()[0]) == ["manifest_unknown_field"], path
