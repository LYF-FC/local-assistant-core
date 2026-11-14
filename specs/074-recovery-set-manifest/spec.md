# Spec 074: Recovery-set manifest and offline verification

**Status: draft for owner review. Nothing here is implemented, frozen, verified, merged or accepted.** Drafting this document changes no implementation status, status counts, verification or owner acceptance, and it is **not** authorization to implement. Implementation requires a separate explicit owner instruction after the owner answers the decisions in section 10. Gate 11 (MVP-05), Gate 6 (DOC-X02) and Gate 10 stay open and unaccepted, and no register row, count or priority changes.

Baseline: `main` at `4a7e62468196fff913df02ac4fb6f60ae7759b83` (merge of PR #37). Companion documents: [plan.md](plan.md) (plan, checklist, analysis) and [tasks.md](tasks.md) (task outline, none started).

This draft follows the repository workflow (specify, clarify, plan, checklist, tasks, analyze): sections 1 to 9 specify, section 10 collects the clarifying decisions, and the plan, checklist and analysis are in `plan.md`.

## 1. Problem and outcome

### 1.1 Problem

A restorer who is handed a backup today has no way to answer, before restoring anything, three separate questions:

1. Is what I was handed exactly what was recorded when the backup was taken (nothing missing, added, truncated or altered)?
2. Was that record made by someone holding the key I independently trust?
3. Is it the backup I am supposed to be using?

The existing recovery tooling answers narrower questions only for Work suppression files (spec 033 authenticates them, spec 034 compares them with an independently retained checkpoint). The restore drill (`scripts/test-db-restore.sh`) hard-codes the expected migration head and checks a sentinel after restoring; nothing defines what a complete backup set is, and nothing verifies a set before restore.

### 1.2 Outcome

An offline command-line tool with two operations:

- `generate` records a **recovery-set manifest**: the exact members of a supplied recovery-set directory (sizes and SHA-256), a declared schema head and ordered migration chain, a declared installation identity, an application and package version record, an optional model digest declaration, and hash references to Work recovery artifacts, authenticated with HMAC under a dedicated recovery key.
- `verify` checks a supplied set and manifest **before any restore** and reports three separate outcomes: integrity, authenticity and freshness (section 2).

`verify` never connects to a database, never writes, and never claims that a set is the latest backup, that restoration will succeed, or that recovery is complete.

### 1.3 What this slice does not claim

It does not establish that the set is the latest backup (section 2.3), that the dump's *contents* belong to the declared installation or are at the declared schema head (section 3.5), that a later restore reads the same bytes that were verified (section 8), or that any recovery objective is met. It is a prerequisite for those claims, not a substitute.

## 2. Integrity, authenticity and freshness are different properties

This separation is mandatory in the command output, the reason codes, the documentation and the tests. No output, field name or message may use "latest", "current", "fresh" or an equivalent unless an independently supplied expected value established it, and then only in the exact form of section 2.3.

### 2.1 A. Integrity

Does the supplied recovery set match its recorded member names, sizes and hashes, and is the manifest well-formed (closed schema, canonical form, no duplicate keys, no unknown fields)?

Integrity is evaluated against the **manifest as supplied**. It says nothing about who produced the manifest. Integrity can be valid for a set and manifest that an attacker made together.

### 2.2 B. Authenticity

Was the manifest authenticated with the expected recovery trust anchor, and does the verifier obtain that trust anchor independently of the supplied set and manifest?

Authenticity requires all of: a protected key file whose public fingerprint equals an **externally supplied expected fingerprint**, a key namespace for this purpose, a key bound to the expected installation, and a valid HMAC over the canonical payload. Authenticity is about the key, not about truth: anyone holding the key can authenticate any manifest (section 6.4).

### 2.3 C. Freshness

Is this the recovery set the owner or recovery process expects to use?

A valid HMAC proves neither freshness nor latest-set status: an older, correctly authenticated manifest remains cryptographically valid forever. The only freshness evidence this slice can produce is a comparison of the supplied manifest's hash with an **externally supplied expected manifest hash**:

- no expected hash supplied: freshness is `freshness_not_established` (the normal, safe default);
- hash supplied and equal: `freshness_validated_against_expected_hash`. This states only that the supplied manifest equals the supplied expected hash. It does not state that the expected hash is the latest backup. That depends entirely on how the expected hash was produced, retained and governed outside this tool (section 5.2);
- hash supplied and different: `freshness_mismatch_with_expected_hash`.

The slice creates no latest-manifest service, no online dependency and no second database authority.

### 2.4 Output model (summary; full definition in section 7)

| Field | Values |
|---|---|
| `integrity` | `integrity_valid`, `integrity_invalid`, `integrity_not_evaluated` |
| `authenticity` | `authenticity_valid`, `authenticity_invalid`, `authenticity_not_evaluated` |
| `freshness` | `freshness_not_established`, `freshness_validated_against_expected_hash`, `freshness_mismatch_with_expected_hash` |
| always present | `point_in_time: true`, `restore_performed: false`, `recovery_complete: false` |

## 3. Requirement and gate mapping, baseline and recovery-set definition

### 3.1 Requirement and gate mapping

| Item | Relationship |
|---|---|
| MVP-05 (Gate 11) | Contributes to "restore ... from protected backups: DB, exact originals, configuration, migration/model manifests ... and test failed/missing/tampered recovery inputs" from `docs/MVP_ACCEPTANCE.md`. Partial contribution only; MVP-05 stays "planned / full acceptance not evidenced". |
| PLATFORM-03 | Contributes to "independent key/source/full-host recovery evidence" by defining and testing set verification; stays partial. |
| DOC-X02 (Gate 6) | **Enabler only.** A verified older manifest can list objects that were later forgotten (section 9.4). This slice does not reconcile forgetting; DOC-X02 stays open. |
| OPS-09 / PLATFORM-02 | **Enabler only.** No backup-freshness observation, no RPO/RTO target, no measured objective is introduced. |

No register row, status, count, priority or acceptance criterion changes. The wording of those requirements is quoted from the register and `docs/MVP_ACCEPTANCE.md`; this spec adds no requirement.

### 3.2 Existing baseline and what is reused

| Existing | Reuse in this slice |
|---|---|
| Spec 033 authenticated manifests: stdlib HMAC-SHA256, full tags, `secrets` key generation, domain-separated fingerprint and MAC, constant-time comparison, fingerprint supplied independently | Same pattern and primitives, under a **new key purpose and new domains**. The Work key and Work modules are not reused or changed. |
| Spec 034 checkpoint rule: an expected manifest hash is an external input, never read from the candidate file | Same rule for the optional expected manifest hash. |
| `app/work_suppression_file.py` protected file handling (no-follow, single-link, owner-only, bounded, exclusive create, fsync of file and parent) and canonical JSON (`sort_keys`, compact separators, `allow_nan=False`), duplicate-key rejection | Same behaviour is required. Whether code is shared or re-implemented is a plan decision constrained by "Work behaviour is unchanged" (`plan.md`). |
| Spec 050 archive layout (`.archive.json` marker, `.archive.lock`, objects `<32 hex>-v<n>.original`, 8192 entries, 128 KiB per object, 64 MiB root) | Defines the archive members a set may contain. |
| `operations.inventory` package metadata | Source of the declared application and package version record. |
| `scripts/test-db-restore.sh` (`pg_dump --format=custom` in the `postgres:17` CI service container; restore into a second database) | The CI drill extends this script. |

**Correction to the proposed scope.** The assignment lists an "installation manifest from Spec 060" as a set member. No such product artifact exists. The spec 060 `BUTLER_INSTALLATION_RESTORE_MANIFEST_FILE` is a temporary file written by the test harness (`scripts/installation-restore-fixtures.py`) to compare a restored record with the original; the installation UUID lives in the database (`installation_config.installation_id`, created at first apply) and in the dump. This spec therefore carries the installation identity as a **declared field in the manifest** (section 3.5), not as a file, and the fixture file is never a recovery-set member.

### 3.3 Permitted recovery-set contents

A recovery set is a single directory (`SET`) containing exactly:

| Member | Path in `SET` | Rule |
|---|---|---|
| Database dump | `database.dump` | Required. One regular file, intended to be `pg_dump --format=custom` output. The tool treats it as opaque bytes. |
| Archive marker | `archive/.archive.json` | Present if and only if the manifest declares an archive. |
| Archive lock file | `archive/.archive.lock` | Present if and only if the archive is declared. |
| Archive objects | `archive/<32 hex>-v<n>.original` | Zero or more, individually enumerated in the manifest. |

Everything else is **declared metadata inside the manifest body**, not a file: the declared installation identity, the schema manifest, the application and package version manifest, the optional model digest declaration, and the Work hash references (section 4). The manifest itself and the key live **outside** `SET` (section 3.4, 5).

Explicitly not members: the Work suppression manifest and checkpoint files (referenced by hash only, decision O2), credentials, passwords, tokens, model weights, `.env` or host configuration, document keys, WAL, exports and the spec 060 harness manifest. Their presence in `SET` is `set_member_unexpected`.

### 3.4 Closed-set semantics

`verify` and `generate` enumerate `SET` with the following rules. Any violation stops with a closed reason code (section 7.3); the first violation found in a fixed order is reported, plus a count of further violations only (never names outside the allowlist).

1. **Descriptor-relative enumeration.** `SET` and `archive/` are opened without following symlinks and read through directory descriptors; names are read once. Entries are processed in ascending order of their raw byte names, independent of filesystem order, locale and case.
2. **Name allowlist.** A path must match one of the permitted patterns of section 3.3 exactly. Object names match `[a-f0-9]{32}-v[1-9][0-9]{0,8}\.original`. Anything else (including `.pending-*` temporaries, editor backups, case variants and Unicode look-alikes) is unexpected.
3. **Path normalization.** Manifest member paths are relative, use `/` only, contain no empty, `.` or `..` segment, no NUL or backslash, are at most 64 bytes per segment and 2 segments in depth, and must be byte-for-byte equal to the allowlisted form (no normalization is performed, so there is exactly one spelling). Absolute paths and traversal are rejected at manifest parse time, before any filesystem access.
4. **Types and links.** Only regular files and the single `archive` directory are permitted. Symlinks, hard-linked files (`st_nlink != 1`), sockets, FIFOs, devices and nested directories are rejected. File types are determined with `fstat` on the opened descriptor, not `lstat` of a path.
5. **Modes.** Files and directories must have no group or other permission bits. (Existing archive modes `0600`/`0700` pass.) A set copied with looser modes fails with `set_member_unsafe_mode`; the tool never changes modes.
6. **Closed world.** The enumerated names must equal the manifest member list exactly: a member in the manifest but absent is `set_member_missing`; a name present but not in the manifest is `set_member_unexpected`; an unexpected directory is `set_directory_unexpected`. Duplicate member names or names differing only by case are `set_enumeration_ambiguous`.
7. **Bounds.** At most 8193 members (the dump plus the existing archive cap of 8192 entries); archive object at most 131072 bytes; archive payload at most 64 MiB (the existing archive limits, so a set cannot describe an archive the adapter would refuse); dump at most 64 GiB (proposed engineering ceiling, see O8). Exceeding a bound is `set_entry_limit_exceeded` or `set_member_size_mismatch` before hashing continues.
8. **Single read per member.** Each member is opened once, `fstat`ed, hashed in a streaming loop with a fixed 1 MiB buffer reading at most declared size plus one byte, and `fstat`ed again. A change of size, inode or modification time, or a read longer than declared, is `set_changed_during_read`. Memory use is constant regardless of dump size.
9. **No content interpretation.** The dump is never parsed. Only the archive marker (at most 256 bytes) is parsed, and only to compare its `root_id` with the declared `archive.root_id` (`archive_marker_mismatch`).

### 3.5 What the declared fields do and do not prove

`verify` has no database connection and does not parse the dump. Therefore:

- The **installation identity** and the **schema head and chain** in the manifest are *operator declarations authenticated by the key*. `verify` checks them against external expected values (section 5) and for internal consistency, but it cannot show that the dump actually contains that installation's data or is at that schema head.
- The CI drill produces *test evidence* that a particular synthetic dump restores at the declared head (it compares the restored `alembic_version` with the manifest). That evidence belongs to the drill, not to `verify`.
- The application and package version manifest is declared and authenticated only. It is never compared with the verifier's environment and is not a compatibility claim.
- The model digest declaration refers to no file in the set and is not checked against any model store.
- The Work hash references are opaque authenticated pass-throughs; the referenced files are not in the set and are not checked.

A later restore slice may bind these claims to the database at restore time; that is out of scope here.

## 4. Manifest format (version 1)

### 4.1 Representation

- UTF-8 JSON, canonical form identical to the existing Work manifests: object keys sorted, separators `,` and `:` with no insignificant whitespace, `allow_nan=False`, no floating-point numbers (integers only), `ensure_ascii` escaping. The file stores exactly the canonical bytes plus no trailing newline.
- The parser **rejects duplicate keys at every depth**, unknown fields at every depth (closed schema, `extra=forbid`), a wrong or missing `schema_version`, non-canonical input (re-serializing the parsed value must reproduce the input bytes exactly), integers outside the declared ranges, strings outside the declared patterns and any size above 4 MiB (`manifest_too_large`).
- A manifest with an unknown `schema_version` is `manifest_schema_unsupported`; there is no best-effort parsing.

### 4.2 Envelope and authentication

```
{
  "schema_version": 1,
  "purpose": "butler.recovery-set.v1",
  "payload": {
    "key_id": "<uuid>",
    "key_fingerprint": "<64 hex>",
    "body": { ... section 4.3 ... }
  },
  "algorithm": "HMAC-SHA256",
  "mac": "<64 hex>"
}
```

- `mac = HMAC-SHA256(key, MAC_DOMAIN || canonical(payload))`, full 256-bit tag, verified with `hmac.compare_digest`.
- `MAC_DOMAIN = b"butler.installation-recovery-set-mac.v1\n"`. The public fingerprint uses a different domain, `b"butler.installation-recovery-set-key-fingerprint.v1\n"`, over public key identity (key id, purpose, installation id, creation time), exactly as spec 033 derives its fingerprint. Both domains are distinct from the Work domains (`butler.synthetic.work-recovery-key-fingerprint.v1`, `butler.synthetic.work-suppression-auth.v2`).
- **Manifest hash** (the freshness handle): `manifest_hash = SHA-256(HASH_DOMAIN || canonical(payload))` with `HASH_DOMAIN = b"butler.installation-recovery-set-manifest-hash.v1\n"`. It covers the key references and the entire body, and excludes the MAC so the hash can be retained independently of the key.
- The payload embeds `key_id` and `key_fingerprint` so a MAC cannot be transplanted to a different key claim.

### 4.3 Body

| Field | Content | Notes |
|---|---|---|
| `set_id` | UUID | Random per generation unless supplied for tests. |
| `created_at` | aware UTC timestamp | Application clock (`identity.now_utc()`); subject to the clock limitation of spec 073 section 1.4.1 and informational only. It is never used to decide freshness. |
| `generator` | `{ "tool_version": "<string>" }` | Fixed pattern, at most 32 characters. |
| `installation` | `{ "installation_id": "<uuid>" }` | **Declared** (section 3.5). |
| `schema` | `{ "head": "<revision id>", "revisions": ["<id>", ...] }` | Ordered oldest to newest; `head` equals the last element; derived by the generator from the migration scripts of its own code, offline. |
| `application` | `{ "api_version": "...", "python_version": "...", "packages": { "fastapi": "...|null", "sqlalchemy": ..., "psycopg": ..., "pydantic": ... } }` | Same four packages as `operations.inventory`; values limited to the existing safe-version pattern or `null`. |
| `model` | `{ "declared": false }` or `{ "declared": true, "tag": "<tag>", "digest": "<64 hex>" }` | Tag and digest follow the existing local-model validators in `app/config.py`. Declaration only. |
| `work_references` | `{ "suppression_manifest_sha256": "<64 hex>|null", "source_checkpoint_sha256": "<64 hex>|null" }` | Hash references only (decision O2), copied by the operator from the retained spec 034 checkpoint records. |
| `archive` | `{ "present": false }` or `{ "present": true, "root_id": "<uuid>", "object_count": <int> }` | `root_id` is read by the generator from the marker. |
| `members` | ordered list of `{ "path": "...", "kind": "dump|archive_marker|archive_lock|archive_object", "size": <int>, "sha256": "<64 hex>" }` | Sorted by raw path bytes; this order is part of the canonical form. |

The body contains metadata and cryptographic references only: no file content, no document text, no personal data, no key material, no host path, no hostname or user name, no timing values.

### 4.4 Determinism

Given identical member bytes, identical operator declarations (installation id, model declaration, Work references), the same key, the same `created_at` and `set_id`, `generate` produces byte-identical output regardless of filesystem enumeration order, locale or platform. Timing is deliberately not stored in the manifest (decision O3); it appears only in command output (section 7.1).

## 5. External trust inputs and provenance

The manifest must not establish its own trust. `verify` accepts trust inputs **only as explicit command-line arguments or the explicit key file argument**. There is no environment-variable, configuration-file, default-path or "same directory" fallback, and no value is ever read from the manifest, the set, a database, an audit event, a log or a previous tool output to satisfy a check.

### 5.1 Inputs

| Input | Argument | Required | What it is checked against | Required provenance |
|---|---|---|---|---|
| Expected key fingerprint | `--expected-key-fingerprint HEX64` | Yes | the fingerprint recomputed from the key file, the payload's `key_fingerprint`, and the MAC | Recorded at key generation in a record kept separately from the key file, the set, the manifest and the database (as in spec 033). |
| Recovery key file | `--recovery-key PATH` | Yes | the namespace, installation binding and fingerprint above | Protected key custody (section 6); never inside `SET`. |
| Expected installation UUID | `--expected-installation-id UUID` | Yes | the key file's installation id and the manifest's declared installation id | An independently retained record of the installation identity, **not** read from the dump, the database or the manifest. |
| Expected schema head | `--expected-schema-head REVISION` | Yes | the manifest's declared `schema.head` | The head the recovery operator intends to restore, chosen independently. An older head than the verifier's code is allowed and expected when restoring an older backup. |
| Expected manifest hash | `--expected-manifest-hash HEX64` | Optional | the computed `manifest_hash`, for freshness only (section 2.3) | An independently governed and retained record of the manifest hash the process expects. |

A **schema policy** that permits more than one head (for example "this head or any newer") is deliberately not defined here; exact match only. Permitting upgrades is a restore-time decision.

### 5.2 Provenance requirements and limits

- Each expected value must come from a record retained independently of the recovery set storage, of the key custody and of the verifier host, so that compromising one of them does not let an attacker supply all of them. The tool cannot verify independence; it can only refuse to take values from the candidate artifacts.
- A supplied expected manifest hash proves only that the supplied manifest equals that hash. It proves the manifest is the latest only if the *source* of that hash is independently governed and retained (who records it, when, where, and how it is updated after each backup). That governance is a process and an owner decision outside this slice (O5).
- A deliberately supplied older hash matches an older manifest. The tool cannot detect that choice.
- `--require-freshness` makes freshness part of the exit status. It without `--expected-manifest-hash` is a usage error (`freshness_requested_without_expected_hash`, exit 2, before any file access).

## 6. Trust anchor and key custody

### 6.1 Recommendation (decision O1, not yet approved)

Use a **dedicated recovery-specific key**, separate from every Work key, application secret, database credential and document key. HMAC-SHA256 under that key authenticates the manifest. This slice generates, provisions and uses **no real key**; tests use synthetic keys created by a test helper only.

### 6.2 Key file and namespace separation

- The key file is JSON bounded at 2 KiB with `schema_version`, `purpose: "installation_recovery_set"`, `key_id`, `installation_id`, `created_at` and 32 bytes of material as 64 hex characters held as a masked secret type. It is read with the protected-file rules (regular, single link, owner-only, no-follow, bounded).
- The `purpose` and the installation binding give namespace separation: a Work key file, a database credential file or any file with another `purpose` fails with `key_namespace_mismatch` and is never interpreted as recovery material; a key bound to installation A fails for installation B with `key_installation_mismatch`.
- Fingerprint and MAC domains are distinct from each other and from every Work domain (section 4.2). Nothing in this slice reads, writes or changes Work keys or Work key files.

### 6.3 Secret handling

Key material never appears in manifests, command output, error messages, log lines, test artifacts, exception text or tracebacks. It is never accepted as an argument or environment value. The command catches all exceptions at its boundary and prints only a reason code. Tests assert absence of the material (and of its hex, base64 and repr forms) across stdout, stderr, files written and captured logs, including for crashing inputs.

### 6.4 HMAC trade-offs (decision O6)

HMAC is symmetric. Consequences the owner must accept or reject:

- Anyone holding the key can authenticate any manifest, including the verifier's host and every copy of the key. There is no non-repudiation and no separation between "can verify" and "can forge".
- A compromised verifier host that has the key can forge a manifest for a malicious set and then "verify" it.
- It matches spec 033, needs no new dependency (no asymmetric library exists in the project) and is simple to test offline.
- An asymmetric signature (for example Ed25519) would let the verifier hold only a public key, so verification would not confer forging power. It would add a dependency, a new key-management model and different failure modes. This draft does **not** assume or introduce asymmetric signatures; it records the choice as O6, recommending HMAC for this slice and a later review if the custody model needs separation of duties.

### 6.5 Custody responsibilities (holder and location are an owner decision, O1)

The draft names no holder or storage location and assumes none is approved. Any future arrangement must satisfy at least:

1. The key and its fingerprint record are held **separately from each other** and separately from the recovery sets they authenticate, so one loss or compromise does not hand an attacker all three.
2. There is an accountable, recorded owner of the key and a defined second person or mechanism able to recover it, so that one person's absence does not lose the ability to authenticate.
3. The key is protected at rest by a mechanism independent of the production host and of the backup storage (the repository's existing documentation refers to a "reviewed encrypted/off-site key policy"; no such policy is present in the repository, so it is a prerequisite that this spec does not create).
4. Access is limited, recorded and reviewable; use of the key for generation is deliberate, not automatic.
5. Recovery of the key is itself rehearsed, because a key that cannot be recovered makes authenticity unverifiable when it matters.
6. The expected-fingerprint record is retained with the same independence as the expected-hash record (section 5.2).

### 6.6 Rotation, replacement, loss and compromise (specification-level only)

| Event | Consequence | Not provided in this slice |
|---|---|---|
| Planned rotation | Create a new key and fingerprint record; new manifests use it. Old manifests verify only with their old key and old fingerprint, which must therefore be retained as long as those manifests are in use. | No rotation command, no key registry, no automatic re-signing. |
| Replacement | Equivalent to rotation after a lost or damaged key file when a copy exists. | No key escrow mechanism. |
| Loss of the key | Authenticity cannot be established for existing manifests. Integrity of a set against its manifest can still be checked, but that proves nothing about origin. New manifests need a new key and a trusted way to re-attest the existing sets. | No recovery of a lost key; no unsigned bypass flag. |
| Compromise | Every manifest authenticated under that key is untrusted, including old ones. Affected sets must be re-validated from known-good sources and re-attested under a new key with a new independently recorded fingerprint. | No revocation list or online status; a revoked key is identified only by the operator's records. |

## 7. Command interface, outputs, reason codes

The module and flag names below are proposals; the observable contract (separate outcomes, closed codes, exit statuses) is what matters.

### 7.1 Operations

`generate` (offline, no database, no network):

```
generate --set DIR --output MANIFEST_FILE --recovery-key KEY_FILE --expected-key-fingerprint HEX64
         --installation-id UUID --schema-head REVISION
         [--model-tag TAG --model-digest HEX64]
         [--work-suppression-manifest-sha256 HEX64] [--work-source-checkpoint-sha256 HEX64]
```

`generate` reads `SET` read-only, applies section 3.4, writes only `MANIFEST_FILE`, and prints the new `manifest_hash`, key references, member count, byte total and elapsed milliseconds. It requires the same expected fingerprint as `verify` so a generator cannot silently use a different key. It is a trusted operator action over a set that the operator is responsible for having quiesced; it detects change *during* its own read only.

`verify` (offline, read-only, no database, no network):

```
verify --set DIR --manifest MANIFEST_FILE --recovery-key KEY_FILE
       --expected-key-fingerprint HEX64 --expected-installation-id UUID --expected-schema-head REVISION
       [--expected-manifest-hash HEX64] [--require-freshness]
```

`MANIFEST_FILE` and `KEY_FILE` must not be inside `SET`, and not inside each other's directory in a way that makes them set members (`paths_overlap`, exit 2).

### 7.2 Evaluation order

1. Trust-input shape: all required inputs present and well-formed; `--require-freshness` implies a hash. Failure: usage error, exit 2, **no file access**.
2. Manifest file: protected read, size, then parse and structure checks (duplicate keys, unknown fields, canonical form, schema version). A failure sets `integrity_invalid` or `integrity_not_evaluated` as defined in the output table and stops.
3. Key file: protected read, namespace, installation binding, fingerprint equals the expected fingerprint.
4. **Authenticity**: payload key references equal the key file's; MAC valid.
5. External bindings: key installation id, declared installation id and expected installation UUID all equal; declared schema head equals the expected head; the declared chain is internally consistent (head is last; no duplicates) and is a prefix of the verifier's own migration chain (`schema_unknown_to_verifier` when the verifier's code does not know a declared revision, `schema_chain_inconsistent` otherwise).
6. **Integrity of the set**: section 3.4 enumeration and hashing. This runs only if authenticity is valid, because hashing a set against an unauthenticated manifest yields no useful claim; otherwise `integrity` is reported as `integrity_not_evaluated` for the set while the structure result stays reported through the reason code.
7. **Freshness**: the optional hash comparison (section 2.3). It never changes `integrity` or `authenticity`.

### 7.3 Output and exit status

The command prints one JSON object with a closed key set; unknown or additional keys are never emitted.

| Key | Meaning |
|---|---|
| `schema_version`, `operation` | `1`; `generate` or `verify` |
| `integrity`, `authenticity`, `freshness` | The enumerations of section 2.4 |
| `reasons` | Ordered list of closed reason codes (empty on full success) |
| `manifest_hash`, `key_id`, `key_fingerprint` | Public references, when computed |
| `member_count`, `member_bytes` | Integers, when the set was enumerated |
| `elapsed_ms` | Tool-measured duration of this run; informational; **not** a recovery-time measurement |
| `point_in_time` | Always `true` |
| `restore_performed`, `recovery_complete` | Always `false` |
| `freshness_note` | Fixed string when freshness is validated: `matches_supplied_expected_hash_only` |

Exit status: `0` when integrity is valid, authenticity is valid, all bindings hold (and, only with `--require-freshness`, freshness is validated); `1` for any verification failure; `2` for usage or trust-input errors. Without `--require-freshness`, an unestablished freshness does not change the exit status, and the output still says so.

Reason codes (closed, stable; additions need a spec change):

| Group | Codes |
|---|---|
| Usage and trust inputs | `trust_input_missing`, `trust_input_malformed`, `freshness_requested_without_expected_hash`, `paths_overlap` |
| Key | `key_file_unsafe`, `key_file_malformed`, `key_namespace_mismatch`, `key_installation_mismatch`, `key_fingerprint_mismatch` |
| Manifest | `manifest_file_unsafe`, `manifest_too_large`, `manifest_malformed`, `manifest_duplicate_key`, `manifest_unknown_field`, `manifest_noncanonical`, `manifest_schema_unsupported`, `manifest_key_reference_mismatch`, `manifest_authentication_failed`, `manifest_path_unsafe` |
| Bindings | `installation_mismatch`, `schema_head_mismatch`, `schema_chain_inconsistent`, `schema_unknown_to_verifier` |
| Set | `set_member_missing`, `set_member_unexpected`, `set_directory_unexpected`, `set_path_unsafe`, `set_member_not_regular`, `set_member_symlink`, `set_member_hardlinked`, `set_member_unsafe_mode`, `set_member_size_mismatch`, `set_member_hash_mismatch`, `set_entry_limit_exceeded`, `set_enumeration_ambiguous`, `set_changed_during_read`, `archive_marker_mismatch` |
| Freshness | `freshness_mismatch_with_expected_hash` |
| Generation | `output_exists`, `output_unsafe`, `io_error` |
| Internal | `internal_error` (no detail) |

Safe error handling: no exception text, no traceback, no path the operator supplied (only the closed code), no file content and no key material is printed. Member names are printed only if they match the allowlist, so they cannot carry arbitrary text. The tool never echoes a supplied expected value that failed to match; it states which check failed.

## 8. Verification-to-restore gap

A successful `verify` is a **point-in-time observation** of the bytes the tool read. Files can change after verification and before restoration, for example by another process, a replaced medium, storage corruption or an attacker with write access to the set. This slice performs no restoration and therefore **does not guarantee that a later restore consumes the bytes that were verified**. The output states `point_in_time: true`, and the documentation and acceptance tests demonstrate the limitation (a file modified after a successful verification is only caught by a second verification).

Future mitigation options, none of which this slice implements: (a) a combined verify-and-stage that copies members into a private staging directory while hashing them, so restore reads the staged, verified copy; (b) re-verification immediately before restore with the restore bound to the manifest hash; (c) hash-while-restoring, so the restore stream is itself verified; (d) restoring from immutable or read-only media; (e) restricting write access to the set between verification and restore. Choosing among them belongs to a restore-slice specification.

## 9. Atomic generation, failure semantics, scope boundaries

### 9.1 Observable guarantees for manifest publication

Specified as guarantees, not as one implementation; an exclusive-create temporary file published with a no-replace atomic link or rename plus `fsync` is a suitable approach.

- **G1 No partial final manifest.** After any interruption (crash, kill, power loss to the extent the filesystem honours `fsync`, I/O error, out of space), the final manifest path either does not exist or contains a complete, valid manifest. Never a prefix, never a mix.
- **G2 No overwrite.** An existing file at the output path is never modified, truncated, replaced or removed. `generate` fails with `output_exists`. There is no replace option in this slice.
- **G3 Temporary files.** Temporaries are created exclusively (never reusing a name), owner-only, in the output directory, with a recognizable prefix and a per-run random token. A run removes its own temporary on every failure it survives. A temporary left by a killed run is never mistaken for a manifest (it is not at the final name), is never deleted by a later run (which cannot prove it created it), and is reported as an informational `stale_temporary_present` note, not a failure.
- **G4 Atomic publication.** The final name appears in one step, fully written and flushed.
- **G5 Durability.** The temporary file is flushed to stable storage before publication and the containing directory is flushed after, so a success return means the manifest survives a subsequent crash on filesystems that honour `fsync`. The documentation states that this depends on the filesystem and storage.
- **G6 Concurrent generation.** Two generators targeting the same output path: exactly one publishes; the other receives `output_exists`; neither leaves a partial file and neither corrupts the other's result. Generators targeting different outputs do not interfere. Concurrent *modification of the set* during generation is not prevented, only detected within the read of each member (`set_changed_during_read`).
- **G7 Filesystem errors.** Any error while reading the set or writing the manifest ends the run with `io_error` (or the specific set code), exit status 1, no final manifest and best-effort removal of the run's own temporary. The tool never reports success when any write, flush or publish step failed.
- **G8 Output path safety.** An output path that is a symlink, a directory, inside `SET`, or whose parent is writable by group or other is `output_unsafe`.

### 9.2 Scope boundaries

In scope: the offline `generate` and `verify` operations; read-only verification; deterministic manifest generation; integrity and authenticity checks; external expected-value inputs; synthetic tests and a CI drill using real `pg_dump` output; stable non-sensitive results.

Out of scope: database writes or migrations; runtime API, UI, worker or compose changes; restoration itself; real keys, real NAS, production hosts or external infrastructure; encryption of backups or archives; backup scheduling, backup-freshness services or any latest-manifest authority; DOC-X02 forgetting reconciliation and non-Work suppression exports; worker liveness or alerting; acceptance of RPO/RTO targets; clean-host recovery claims; key management tooling (a real key-generation command is deferred, decision O9).

### 9.3 Data-flow statement (constitution, principle I)

Nothing leaves the private environment. The tool opens no network connection and no database connection, runs offline on local files, and sends no content to any provider or model. The manifest is a local file whose handling is the operator's responsibility.

### 9.4 Security and privacy constraints

- **Data ownership.** The tool owns no data: the dump, archive and Work artifacts remain the authority; the manifest is evidence about files, never a source of truth for business records, never an approval or authority to restore, and never a second authority over forgetting decisions.
- **Metadata disclosure.** Archive object names encode a document UUID and revision, and sizes are recorded. A manifest therefore discloses which document identifiers and revisions existed and their sizes, and an older manifest keeps naming objects that were later **forgotten and purged**. The manifest must be treated as sensitive operational metadata, retained under the same access control as backups, and its retention as a forgetting concern is recorded for the owner (O2). A manifest listing a forgotten object is **valid evidence about an old set**; it is never permission to restore that object. Forgetting reconciliation (DOC-X02) must still run on any restored older data.
- **Least privilege.** The tool runs as an unprivileged user with read access to the set and key and write access to the output directory only. It does not need and must not use the runtime database role, the migration owner or any service credential.
- **Bounded resource use.** Constant memory (1 MiB buffer), bounded member count, bounded manifest and key size, one pass per member, no recursion, no network and no unbounded loops.

## 10. Owner decisions and unresolved questions

Recommendations are not approved until the owner confirms them.

| ID | Decision | Recommendation | Consequence |
|---|---|---|---|
| **O1** | Trust anchor and key custody | A dedicated recovery-specific offline HMAC key, separate from Work and application keys (section 6). **The key holder and storage arrangement are explicitly not decided** and must be decided by the owner before any implementation that depends on real key custody. | Without a custody decision, only synthetic-key engineering is possible; no real set can be authenticated. |
| **O2** | Manifest scope | Work suppression artifacts are referenced **by hash only**; archive objects are individually hashed. Also decide how long manifests may be retained, given that old manifests name forgotten document identifiers (section 9.4). | Individual hashing makes the manifest grow with the archive (about 1.6 MB at the 8192-entry cap) and discloses identifiers; hash-only Work references keep Work content out of the set. |
| **O3** | RPO/RTO | This slice reports tool-measured durations only in command output and accepts no recovery target. The 1 hour / 24 hour / 4 hour candidates in `docs/MVP_ACCEPTANCE.md` stay proposals. | No claim about recovery objectives results from this slice. |
| **O4** | Restart evidence | Process-kill tests for approved-job and reminder workers stay in a separate later batch. | Gate 10 restart evidence for those workers remains open. |
| **O5** | Freshness trust | The slice performs an optional comparison against an independently supplied expected manifest hash and creates no latest-manifest authority. Who records and governs that hash after each backup is outside this slice. | A matching hash proves equality with the supplied value, never that the set is the latest. |
| **O6** | HMAC versus asymmetric signatures | HMAC for this slice (section 6.4). | The verifier holds forging power. Revisit if separation of duties is needed. |
| **O7** | Installation identity source | The installation UUID is an operator-declared, key-authenticated field checked against an independently retained expected value (section 3.5). Binding it to the database is deferred to a restore slice. | `verify` cannot show that the dump belongs to that installation. |
| **O8** | Numeric ceilings | Dump at most 64 GiB; manifest at most 4 MiB; key file at most 2 KiB; 8193 members; 1 MiB read buffer. These are engineering ceilings, not capacity or RPO/RTO claims. | `docs/MVP_ACCEPTANCE.md` requires numeric thresholds to be defined before implementation; unconfirmed values are not passing evidence. |
| **O9** | Key-generation tooling | No real key-generation command in this slice; tests use a synthetic helper. A minimal offline key generator can follow once custody (O1) is decided. | Operators cannot create a real recovery key with this slice alone. |

Unresolved questions (not decisions this draft takes):

1. Is a separate `archive`-optional set sufficient, or must the first real procedure always include the archive?
2. Should the recovery-set directory also be allowed to carry a plain-text, non-authoritative operator note? (This draft says no, to keep the closed set minimal.)
3. After this slice, should the restore drill be changed to restore only from a staged copy that `verify` produced (section 8, option a)? That is a restore-slice question.

## 11. Acceptance criteria, adversarial tests and evidence boundaries

All tests use synthetic data and synthetic keys. Tests that need no database run in the ordinary backend suite; the drill that uses a real dump runs in the hosted `postgres:17` service container. No browser tests are required because the slice has no UI.

### 11.1 Acceptance criteria

1. **A1 Valid set.** A synthetic set (a dump file, an archive with marker, lock and several objects) with a manifest generated under a synthetic key verifies with `integrity_valid`, `authenticity_valid`, `freshness_not_established`, exit 0.
2. **A2 Separation.** Every output, reason code and document keeps the three properties apart; a unit test asserts the output key set and that the strings "latest", "current" and "up to date" never appear in any output.
3. **A3 Deterministic generation** (section 4.4), including enumeration-order independence.
4. **A4 Closed set**: all violations of section 3.4 are rejected with their closed codes and nothing is read outside the allowlist.
5. **A5 External trust inputs**: every required input is mandatory; none is taken from candidate files; the tool refuses to run with a missing or malformed input before touching any file.
6. **A6 Freshness never overstates**: section 2.3 and the tests below.
7. **A7 Atomic generation**: G1 to G8.
8. **A8 No secrets or foreign paths in any output** (section 6.3, section 7.3).
9. **A9 Point-in-time limitation demonstrated** (section 8).
10. **A10 No database, network or write to the set**: asserted by running the verifier with sockets disabled (the suite already uses `--disable-socket`) and a read-only set, and by a test that fails if the tool opens a database connection or writes inside `SET`.
11. **A11 Work behaviour unchanged**: the existing Work suppression and authentication tests pass unmodified; no Work module changes.
12. **A12 No migration**: the alembic revision list and head are unchanged by the implementation (head stays whatever `main` has at implementation time), and the CI drill still asserts the restored head.

### 11.2 Positive and negative test matrix

| # | Case | Expected |
|---|---|---|
| T1 | Valid recovery set | A1 outcome |
| T2 | Missing required file (`database.dump`; an archive object listed in the manifest) | `set_member_missing`, integrity invalid |
| T3 | Unexpected extra file; unexpected extra directory; stray `.pending-*` file | `set_member_unexpected` / `set_directory_unexpected` |
| T4 | Size mismatch (truncated, extended) | `set_member_size_mismatch` |
| T5 | Hash mismatch with unchanged size (one flipped byte) | `set_member_hash_mismatch` |
| T6 | Symlink member; symlinked `SET`; symlinked archive directory; FIFO, socket and device substitutes; hard-linked member | `set_member_symlink` / `set_member_not_regular` / `set_member_hardlinked` |
| T7 | Absolute path, `..` traversal, backslash, NUL, empty segment, over-length segment, case-variant duplicate, Unicode look-alike in a manifest member | `manifest_path_unsafe` / `set_enumeration_ambiguous`, no filesystem access beyond the set |
| T8 | Duplicate JSON key at top level and nested | `manifest_duplicate_key` |
| T9 | Unknown field at every depth | `manifest_unknown_field` |
| T10 | Malformed JSON; valid JSON that is not canonical (whitespace, key order, escapes) | `manifest_malformed` / `manifest_noncanonical` |
| T11 | Unsupported or missing `schema_version`; wrong `purpose` | `manifest_schema_unsupported` |
| T12 | Oversized manifest; oversized key file | `manifest_too_large` / `key_file_unsafe` |
| T13 | Missing key file; unreadable; wrong mode; symlink; group-readable; hard-linked | `key_file_unsafe` |
| T14 | Incorrect key (valid format, different material) with its own correct fingerprint | `manifest_authentication_failed` / `manifest_key_reference_mismatch` |
| T15 | Correct key with an incorrect expected fingerprint | `key_fingerprint_mismatch` |
| T16 | Wrong namespace: a spec 033 Work key file used as the recovery key | `key_namespace_mismatch` |
| T17 | Wrong installation namespace: key bound to installation B, expected installation A | `key_installation_mismatch` |
| T18 | Wrong installation UUID (manifest declares B, expected A) with a correct key | `installation_mismatch` |
| T19 | Schema head mismatch; declared chain with a duplicate or wrong tail; a declared revision the verifier does not know | `schema_head_mismatch` / `schema_chain_inconsistent` / `schema_unknown_to_verifier` |
| T20 | `--require-freshness` with no expected hash | `freshness_requested_without_expected_hash`, exit 2, no file read |
| T21 | A correctly authenticated **older** manifest (valid set at the time) with no external expected hash | integrity valid, authenticity valid, **`freshness_not_established`**, exit 0 |
| T22 | The same older manifest with an expected hash that belongs to a newer manifest | `freshness_mismatch_with_expected_hash`; with `--require-freshness` exit 1 |
| T23 | A manifest equal to the supplied expected hash | `freshness_validated_against_expected_hash` and `freshness_note: matches_supplied_expected_hash_only`; no output string says latest, current or fresh |
| T24 | Key rotation: manifest under key K1 verified with K2 and fingerprint(K2); with K1 and fingerprint(K2); with K1 and fingerprint(K1) | the first two fail with `manifest_key_reference_mismatch` / `key_fingerprint_mismatch`; the third passes |
| T25 | Cross-installation substitution: a complete valid set and manifest for installation B presented for installation A, with B's key and with A's key | `installation_mismatch` / `key_installation_mismatch` / `manifest_authentication_failed` |
| T26 | Manifest and set re-created together by an attacker without the key | authenticity invalid; integrity not evaluated for the set |
| T27 | Interrupted generation: the generator is killed with SIGKILL at controlled points (before the temporary is complete; after it is flushed, before publication) | no manifest at the final path; a following `generate` succeeds; the leftover temporary is not mistaken for a manifest and not deleted |
| T28 | Existing destination manifest | `output_exists`; the existing bytes are unchanged |
| T29 | Concurrent generation to one output path (several processes) | exactly one succeeds; the others `output_exists`; the published manifest verifies |
| T30 | Concurrent generation to different outputs | all succeed and are identical when inputs are identical |
| T31 | Filesystem errors (read-only output directory, full filesystem simulated, member removed mid-run) | `io_error` or `set_changed_during_read`; no final manifest |
| T32 | File modified after a successful verification | the first result stands as a point-in-time observation; a second `verify` fails; the test is named as a demonstration of the limitation |
| T33 | Key material in output | the key bytes, hex, base64 and repr are absent from stdout, stderr, written files and logs, including for crashing inputs |
| T34 | Output allowlist | no host path, exception text or traceback appears for any failing case |
| T35 | Bounds: 8194 members; oversize object; manifest at the limit and one byte over | the specified codes; constant memory (a large synthetic sparse member is hashed without loading it) |
| T36 | Manifest and set paths overlap (`MANIFEST` inside `SET`, key inside `SET`) | `paths_overlap`, exit 2 |

### 11.3 PostgreSQL and real-set drill (hosted CI, `postgres:17` service container)

Extend `scripts/test-db-restore.sh` (no application code change beyond the new tool):

1. Take the existing real `pg_dump --format=custom` output and the existing independently copied archive directory, and assemble a set directory from them.
2. Generate a synthetic recovery key with the test helper, record its fingerprint outside the set, and `generate` a manifest with the real installation UUID read by the harness from the source database (the harness plays the operator who declares it).
3. `verify` the set (valid), then verify mutated copies of the set for the negative classes that need a real dump and archive (flipped byte in the dump, removed archive object, extra archive object, truncated dump, swapped dump from a different synthetic installation, older manifest against a newer set).
4. Restore the dump with `pg_restore` as today and assert that the restored `alembic_version` equals the manifest's declared head, and that the restored installation id equals the declared installation id. This is drill **evidence** for the declared fields on this synthetic dump; `verify` itself still asserts nothing about the dump contents.
5. Record the tool-reported `elapsed_ms` values in the drill log as informational synthetic timings.

### 11.4 Restart and recovery evidence

The generator is stateless; its restart evidence is T27 to T29 (kill, then recover by a fresh process, no partial output). There is no daemon to restart. Evidence that a *restored system* works is the existing restore drill, unchanged.

### 11.5 Migration and downgrade

None. The slice adds no migration, no schema change, no grant and no database object. The acceptance test A12 asserts that the migration head is unchanged by the implementation and that the existing single-head and downgrade tests pass unmodified. There is no downgrade path to test because there is no schema change.

### 11.6 Evidence boundaries

The synthetic CI drill establishes a **test result for the defined hosted CI environment only** (the `postgres:17` service container, synthetic data, a synthetic generated key). It does **not** establish:

- independent verification (a reviewer other than the implementer re-checking at an exact `main` revision);
- real key custody, a real holder or a real storage arrangement;
- that any set is the latest backup;
- a clean-host rehearsal;
- RPO or RTO achievement;
- real NAS or production recoverability;
- owner acceptance.

### 11.7 What would still be required, in order

1. Implementation merged with PR evidence (merge commit and PR-head and merge-commit CI recorded separately).
2. Independent verification at an exact `main` revision, with full rather than scope-reduced coverage.
3. An owner decision on key holder and custody (O1), the independently retained fingerprint and expected-hash records (O5), and a reviewed procedure that uses them on a real set.
4. A clean-host rehearsal on an independent compatible host (a separate gate, not this slice).
5. Owner acceptance naming environment and scope.

## 12. Dependencies and blockers

- **Dependencies:** none new. Python standard library (`hmac`, `hashlib`, `secrets`, `json`, `os`, `stat`), the already-present Pydantic models pattern, and existing modules read-only. No new package, service, schema, grant or compose change.
- **Decisions required before implementation that touches real keys:** O1 (custody), O5 (freshness record governance) and O6.
- **Decisions required before any implementation at all:** O8 (numeric ceilings). The remaining decisions can be confirmed together with scope approval.
- **Blockers for the wider recovery programme (not this slice):** an independent clean compatible host, a reviewed key-recovery policy, DOC-X02 reconciliation design for non-Work records.
