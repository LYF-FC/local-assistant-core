"""Command line: argument parsing, closed JSON output, exit statuses, exception boundary.

Trust inputs are accepted only as explicit arguments (spec 5): there is no environment,
configuration-file, default-path or "same directory" fallback, and no test-only limit or fault
option exists here.
"""

import json
import os
import re
import sys
import types

from app.recovery_set.format import CodedError
from app.recovery_set.generate import generate
from app.recovery_set.result import Result
from app.recovery_set.verify import verify

_HEX64 = re.compile(r"[a-f0-9]{64}")
_UUID = re.compile(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}")
_REVISION = re.compile(r"[A-Za-z0-9_]{1,64}")
_TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,96}:[A-Za-z0-9_.-]{1,30}")


_COMMON_OPTIONS = ("set", "recovery-key", "expected-key-fingerprint", "expect-archive")
GENERATE_OPTIONS = (
    *_COMMON_OPTIONS,
    "output",
    "installation-id",
    "schema-head",
    "model-tag",
    "model-digest",
    "work-suppression-manifest-sha256",
    "work-source-checkpoint-sha256",
)
VERIFY_OPTIONS = (
    *_COMMON_OPTIONS,
    "manifest",
    "expected-installation-id",
    "expected-schema-head",
    "expected-manifest-hash",
)
VERIFY_FLAGS = ("require-freshness",)
_OPERATIONS = {"generate": (GENERATE_OPTIONS, ()), "verify": (VERIFY_OPTIONS, VERIFY_FLAGS)}
_NEGATIVE_NUMBER = re.compile(r"-\d+|-\d*\.\d+")


def _option_like(argument, options):
    """Classify one argument the way the previous ``argparse`` parser did, without ``argparse``.

    Returns ``None`` for a value (positional-looking) argument, ``(name, explicit)`` for an option
    (``explicit`` is the text after ``=`` or ``None``), and raises for an ambiguous prefix. An argument
    that starts with ``-`` but names no option is an unknown option and is a malformed input.

    ``argparse`` was replaced here because its constructor and error paths translate messages
    through ``gettext``, which looks for catalogs on disk under any locale other than ``C``; that
    is filesystem access before a missing or malformed input is refused (spec 11.1 A5). This
    parser reads only the argument strings: no file, no locale and no environment.
    """
    if not argument or argument[0] != "-" or len(argument) == 1:
        return None
    if argument in {f"--{name}" for name in options}:
        return argument[2:], None
    prefix, separator, explicit = argument.partition("=")
    if separator and prefix in {f"--{name}" for name in options}:
        return prefix[2:], explicit
    if argument.startswith("--"):
        matches = [name for name in options if f"--{name}".startswith(prefix)]
        if len(matches) > 1:
            raise CodedError("trust_input_malformed")
        if matches:
            return matches[0], (explicit if separator else None)
    if _NEGATIVE_NUMBER.fullmatch(argument) or " " in argument:
        return None
    raise CodedError("trust_input_malformed")


def parse_arguments(argv):
    """Closed argument parser: the operation, then ``--option value`` or ``--option=value``.

    Every option is optional here (``parse_trust`` enforces the required set). A repeated option
    keeps its last value, as before. Anything else (no or unknown operation, an unknown or
    ambiguous option, a missing option value, a stray value, ``--``, or an explicit value on a
    flag) is ``trust_input_malformed``.
    """
    arguments = list(argv)
    if not arguments or arguments[0] not in _OPERATIONS:
        raise CodedError("trust_input_malformed")
    options, flags = _OPERATIONS[arguments[0]]
    values = dict.fromkeys(GENERATE_OPTIONS + VERIFY_OPTIONS + VERIFY_FLAGS)
    chosen = {"operation": arguments[0]}
    index = 1
    while index < len(arguments):
        argument = arguments[index]
        index += 1
        if argument == "--":
            raise CodedError("trust_input_malformed")
        found = _option_like(argument, (*options, *flags))
        if found is None:
            raise CodedError("trust_input_malformed")
        name, explicit = found
        if name in flags:
            if explicit is not None:
                raise CodedError("trust_input_malformed")
            chosen[name] = True
            continue
        if explicit is None:
            if index >= len(arguments) or arguments[index] == "--":
                raise CodedError("trust_input_malformed")
            explicit = arguments[index]
            if _option_like(explicit, (*options, *flags)) is not None:
                raise CodedError("trust_input_malformed")
            index += 1
        chosen[name] = explicit
    values.update(chosen)
    attributes = {name.replace("-", "_"): value for name, value in values.items()}
    attributes["require_freshness"] = bool(attributes["require_freshness"])
    return types.SimpleNamespace(**attributes)


def _require(args, names):
    for name in names:
        if getattr(args, name) is None:
            raise CodedError("trust_input_missing")


def _match(value, pattern):
    if value is not None and not pattern.fullmatch(value):
        raise CodedError("trust_input_malformed")


def _inside(path, directory):
    """Lexical containment of two absolute, normalised paths (no filesystem access)."""
    return os.path.commonpath([path, directory]) == directory


def _spellings(path):
    """The lexical spelling and the symlink-resolved spelling of one operator path.

    ``abspath`` removes ``.``, ``..`` and redundant separators but cannot see symlinks;
    ``realpath`` resolves existing symlinked components (a stat of the path components only,
    never a read of any content). A path that overlaps in either spelling is refused.
    """
    lexical = os.path.abspath(path)
    return {lexical, os.path.realpath(lexical)}


def _same_existing_file(first, second):
    try:
        return os.path.samestat(os.stat(first), os.stat(second))
    except OSError:
        return False


def _overlaps(set_path, key_path, file_path):
    """Stage-1 ``paths_overlap`` test (spec 3.4, 7.3.0).

    This is a path-shape pre-check made before any file content is touched, on the path names
    as they are at this moment. It does not close a race: a name can be replaced after it
    returns. What refuses links is the later opens, which walk every component of the SET, key,
    manifest and output-directory paths with ``O_NOFOLLOW`` relative to pinned directory
    descriptors (``fsset.open_directory_nofollow``), so a symlink in any position is refused and
    a component swapped after the walk cannot redirect an operation made through the pinned
    descriptor. A name swapped *between two components of the walk* is refused by that
    component's own no-follow open.
    """
    sets, keys, files = _spellings(set_path), _spellings(key_path), _spellings(file_path)
    for directory in sets:
        if any(_inside(path, directory) for path in keys | files):
            return True
    if keys & files:
        return True
    return _same_existing_file(key_path, file_path)


def parse_trust(argv):
    """Stage 1: shape of every trust input, before any file is touched."""
    args = parse_arguments(argv)
    common = ["set", "recovery_key", "expected_key_fingerprint", "expect_archive"]
    if args.operation == "generate":
        _require(args, [*common, "output", "installation_id", "schema_head"])
        _match(args.installation_id, _UUID)
        _match(args.schema_head, _REVISION)
        _match(args.model_digest, _HEX64)
        _match(args.model_tag, _TAG)
        _match(args.work_suppression_manifest_sha256, _HEX64)
        _match(args.work_source_checkpoint_sha256, _HEX64)
        if (args.model_tag is None) != (args.model_digest is None):
            raise CodedError("trust_input_malformed")
    else:
        _require(args, [*common, "manifest", "expected_installation_id", "expected_schema_head"])
        _match(args.expected_installation_id, _UUID)
        _match(args.expected_schema_head, _REVISION)
        _match(args.expected_manifest_hash, _HEX64)
        if args.require_freshness and args.expected_manifest_hash is None:
            raise CodedError("freshness_requested_without_expected_hash")
    _match(args.expected_key_fingerprint, _HEX64)
    if args.expect_archive not in {"present", "absent"}:
        raise CodedError("trust_input_malformed")
    file_path = args.output if args.operation == "generate" else args.manifest
    if _overlaps(args.set, args.recovery_key, file_path):
        raise CodedError("paths_overlap")
    trust = {
        "set": args.set,
        "key": args.recovery_key,
        "key_fingerprint": args.expected_key_fingerprint,
        "expect_archive": args.expect_archive,
    }
    if args.operation == "generate":
        trust.update(
            output=args.output,
            installation_id=args.installation_id,
            schema_head=args.schema_head,
            model_tag=args.model_tag,
            model_digest=args.model_digest,
            work_suppression_manifest_sha256=args.work_suppression_manifest_sha256,
            work_source_checkpoint_sha256=args.work_source_checkpoint_sha256,
        )
    else:
        trust.update(
            manifest=args.manifest,
            installation_id=args.expected_installation_id,
            schema_head=args.expected_schema_head,
            expected_manifest_hash=args.expected_manifest_hash,
            require_freshness=args.require_freshness,
        )
    return args.operation, trust


def run(argv):
    """Returns (output dict, exit status). Only closed codes ever leave this function."""
    operation = "verify"
    try:
        operation, trust = parse_trust(argv)
        result = generate(trust) if operation == "generate" else verify(trust)
    except CodedError as error:
        operation = _operation_hint(argv, operation)
        result = Result(operation, publication="not_published" if operation == "generate" else None)
        result.reason(error.code)
    except Exception:  # noqa: BLE001 - exception boundary: only a closed code leaves
        result = Result(operation)
        result.reason("internal_error")
    return result.to_dict(), result.exit_status()


def _operation_hint(argv, default):
    return argv[0] if argv and argv[0] in {"generate", "verify"} else default


def main(argv=None):
    output, status = run(sys.argv[1:] if argv is None else argv)
    sys.stdout.write(json.dumps(output, sort_keys=True, separators=(",", ":")) + "\n")
    return status
