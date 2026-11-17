# Spec 074: Recovery-set manifest and offline verification

**Status: FROZEN (owner decision of 14 November 2026). Not implemented, not verified, not merged, not accepted. Freezing is not implementation authorization: implementation, including synthetic-only implementation, requires a separate explicit owner instruction.** Gate 11 (MVP-05), Gate 6 (DOC-X02) and Gate 10 stay open and unaccepted, and no register row, count, priority, gate or acceptance status changes.

> **Freeze record.** On 14 November 2026 the owner reviewed this specification and explicitly approved it and decided to freeze it. **The frozen revision is the content of commit `f903237a69e6e2eeeef8b057abef3fc618a27630`** on branch `codex/spec-074-recovery-set-manifest` (the revision the owner reviewed, after the owner decisions and corrections of 14 November 2026). The commit that records this freeze changes only the status wording, this record and the freeze-related task and plan entries; it does not alter the specification's requirements, interfaces, decisions, deferrals or limitations. Any later change to the substance of this specification needs a new explicit owner decision and a new recorded revision. Baseline check at freeze: `main` is `e3e4d3d1da598f178068a32bf458ce4a7ccf4dd2`; the four commits on `main` not in this branch are PR #38 (documentation reconciliation of specs 071 to 073, project status and generated overview files) and touch no file, interface, migration, dependency or assumption of this specification; the migration head on `main` is still `0038_work_status_audit_category`.
>
> **Freeze does not authorize:** implementation of any kind; real key generation, provisioning or custody; real recovery-set generation or verification; operational use or recovery-readiness claims; any change to migrations, schemas, permissions, runtime configuration or deployment; any change to Gate 10, Gate 11, OPS-09, OPS-10, DOC-X02 or wider recovery status. **All deferred decisions of section 10.2 remain deferred, and the 64 GiB figure remains an unapproved placeholder.**

> **Post-freeze clarification (owner-approved 16 November 2026, Europe/Paris; recorded separately from, and not part of, the freeze above).** The owner explicitly decided to retain the verification order of sections 2.5, 6.2 and 7.2 (the key's installation binding is checked before the key references and the MAC) and to correct the one expected-code cell of T25 that contradicted it: for T25's second scenario (installation A's key and fingerprint presented with installation B's manifest) the expected rejection is `key_installation_mismatch`; the frozen text read `manifest_authentication_failed` or `manifest_key_reference_mismatch`. The first and third T25 scenarios, every other test, and every requirement, interface, state, exit status, precedence and deferral are unchanged. This corrects an internal inconsistency; it is not a new freeze and does not change the freeze date or the frozen reference above (`f903237a69e6e2eeeef8b057abef3fc618a27630`), which are kept as they were. **The text of this document therefore contains this one later correction and is not byte-identical to the content of that originally frozen revision.** Decision record: [DECISIONS.md](../../DECISIONS.md), entry of 16 November 2026.

> **Post-freeze clarification (owner-approved 17 November 2026, Europe/Paris; recorded separately from, and not part of, the freeze above or the 16 November 2026 clarification).** The owner explicitly approved a bounded exception to the stage-1 "no file access" wording of sections 2.5 and A5. A missing or malformed argument shape (every required argument must be present and every shape valid, including parser errors) is still rejected with **no** filesystem access. Only after that, the stage-1 overlap pre-check (`paths_overlap`) may perform filesystem *metadata* checks solely to detect overlapping paths and aliases, as the implementation does: `lstat` and `readlink` of the components of each supplied path (symlink resolution) and `stat` with a same-file comparison of the key and the manifest or output path. It performs no open, no read of file content, no enumeration of directory contents and no write or publication. An overlap rejection stays `paths_overlap`, exit 2, all four states `*_not_evaluated`. The existing no-follow protected opens, single-link checks, rejections and the documented race limitation are unchanged. This is not a general exception for stage-1 file access and not a statement that metadata access is never file access; it authorizes no acceptance, no operational activity and no change to C1 to C5. The freeze date and reference above (`f903237a69e6e2eeeef8b057abef3fc618a27630`) and the 16 November 2026 T25 correction are kept as they were. **The text of this document therefore contains two later, separately recorded clarifications (16 and 17 November 2026) and is not byte-identical to the content of the originally frozen revision.** Decision record: [DECISIONS.md](../../DECISIONS.md), entry of 17 November 2026.

Drafting baseline: `main` at `4a7e62468196fff913df02ac4fb6f60ae7759b83` (merge of PR #37). `main` has since advanced to `e3e4d3d1da598f178068a32bf458ce4a7ccf4dd2` (merge of PR #38, documentation only, touching no file this spec depends on). Companion documents: [plan.md](plan.md) (plan, checklist, analysis) and [tasks.md](tasks.md) (task outline, none started).

This specification followed the repository workflow (specify, clarify, plan, checklist, tasks, analyze): sections 1 to 9 specify, section 10 records the owner's decisions, deferrals and the questions that remain, and the plan, checklist and analysis are in `plan.md`.

## 0. Scope and assurance statement

**This specification verifies the integrity and authenticity of a defined backup set. It does not establish complete recoverability, successful restoration, configuration completeness, credential availability, key recoverability, or clean-host readiness.** A successfully verified set is not a complete or restorable recovery environment. The name "recovery-set manifest" is retained for continuity; it names a manifest over a defined backup set, not a claim of recoverability.

Material exclusions (none is provided, checked or implied by this specification):

- configuration and environment manifests;
- model manifests (beyond one optional declared digest) and migration manifests (beyond one declared revision chain);
- credential and secret recovery;
- recovery-key custody and availability;
- clean-host rehearsal;
- RPO/RTO validation;
- forgetting reconciliation across non-Work data and derived artifacts;
- restoration, staging, database writes and migration execution.

## 1. Problem and outcome

### 1.1 Problem

A restorer who is handed a backup today has no way to answer, before restoring anything, three separate questions:

1. Is what I was handed exactly what was recorded when the backup was taken (nothing missing, added, truncated or altered)?
2. Was that record made by someone holding the key I independently trust?
3. Is it the backup I am supposed to be using?

The existing recovery tooling answers narrower questions only for Work suppression files (spec 033 authenticates them, spec 034 compares them with an independently retained checkpoint). The restore drill (`scripts/test-db-restore.sh`) hard-codes the expected migration head and checks a sentinel after restoring; nothing defines what a backup set is, and nothing verifies a set before restore.

### 1.2 Outcome

An offline command-line tool with two operations:

- `generate` records a **manifest** for a supplied backup-set directory: the exact members (sizes and SHA-256), a declared schema head and ordered migration chain, a declared installation identity, an application and package version record, an optional model digest declaration, and hash references to Work recovery artifacts, authenticated with HMAC under a dedicated recovery key.
- `verify` checks a supplied set and manifest **before any restore** and reports separate integrity, authenticity and freshness results, plus a result for the externally supplied expectations (section 2).

`verify` never connects to a database, never writes, and never claims that a set is the latest backup, that restoration will succeed, or that recovery is complete.

### 1.3 What this slice does not claim

It does not establish that the set is the latest backup (section 2.3), that the dump's *contents* belong to the declared installation or are at the declared schema head (section 3.5), that a later restore reads the same bytes that were verified (section 8), or that any recovery objective is met. It is a prerequisite for those claims, not a substitute.

## 2. Integrity, authenticity and freshness are different properties

This separation is mandatory in the command output, the reason codes, the documentation and the tests. No output, field name or message may use "latest", "current", "fresh" or an equivalent. The only freshness states are `freshness_not_evaluated`, `freshness_match` and `freshness_mismatch`, and `freshness_match` is defined in section 2.3 as equality with a supplied value and nothing more.

### 2.1 Integrity

Is the manifest well-formed (closed schema, canonical form, no duplicate keys, no unknown fields) **and** does the supplied set match its recorded member names, sizes and hashes under the closed-set rules of section 3.4?

Integrity is evaluated against the **manifest as supplied** and says nothing about who produced it. Integrity can be valid for a set and manifest that an attacker made together.

### 2.2 Authenticity

Was the manifest authenticated by the recovery key the verifier was independently told to expect?

Authenticity requires all of: a protected key file in the recovery namespace whose **keyed fingerprint** equals an externally supplied expected fingerprint, a key whose installation binding equals the installation id declared in the manifest (the key-authenticated installation identity; `key_installation_mismatch` otherwise), payload key references equal to that key, and a valid HMAC over the canonical payload. Authenticity concerns the key and the MAC. It is not truth: **every holder of the secret can verify manifests and also create valid ones** (section 6.4).

### 2.3 Freshness

Freshness is only a comparison of the supplied manifest's hash with an **independently supplied expected manifest hash**:

- no expected hash supplied: `freshness_not_evaluated`. This is the normal default, not a failure;
- the comparison could not be performed safely (section 2.5 precedence): `freshness_not_evaluated`, with the cause in `reasons`;
- hash supplied and equal: `freshness_match`. This states only that the supplied manifest equals the supplied value. It does **not** state that the expected value is current, authoritative or the latest. That depends entirely on how it was produced, retained and governed outside this tool (section 5.2);
- hash supplied and different: `freshness_mismatch`.

An expected hash does not authenticate a manifest, and a valid HMAC does not establish freshness: an older, correctly authenticated manifest stays cryptographically valid forever. The slice creates no latest-manifest service, no online dependency and no second database authority. Freshness or latest-set status is never claimed without a separately governed, independently supplied source of authority.

### 2.4 Expectations

The external expectations (installation UUID, schema head, archive presence) are compared with the **authenticated declared values** after authenticity is valid. The comparison of the declared installation id with the independently supplied expected UUID belongs here, not to authenticity: authenticity establishes only that the key and the manifest agree about the installation, and `expectations` establishes that it is the installation the operator expected. Their result is reported separately as `expectations`, so that "authentic and intact" never hides "but not the installation, schema or shape I expected".

### 2.5 Complete result-state model

Output fields (every `verify` output contains all four):

| Field | Values | Meaning |
|---|---|---|
| `integrity` | `integrity_valid` | The manifest parsed as well-formed **and** the closed-set check of the set passed. |
| | `integrity_invalid` | The manifest could not be read safely or is malformed, **or** the set contradicts it. At least one integrity reason is listed. |
| | `integrity_not_evaluated` | The set check was not attempted because an earlier stage failed or was skipped (usage error, authenticity not valid). |
| `authenticity` | `authenticity_valid` | Key, namespace, keyed fingerprint, key references and MAC all verified. |
| | `authenticity_invalid` | The key file is unusable or untrusted, or the key references or MAC fail. A reason is listed. |
| | `authenticity_not_evaluated` | Not attempted: usage error, or the manifest could not be parsed. |
| `expectations` | `expectations_met` | Installation UUID, schema head and archive presence each equal the supplied expectation. |
| | `expectations_not_met` | At least one differs. Reasons name which. |
| | `expectations_not_evaluated` | Authenticity is not valid or the manifest did not parse. |
| `freshness` | `freshness_not_evaluated`, `freshness_match`, `freshness_mismatch` | Section 2.3. |

**Precedence** (stages run in this order and a later stage never upgrades an earlier failure):

1. Usage and trust-input shape. Failure: exit 2, all four fields `*_not_evaluated`. A missing or malformed argument shape (including every parser error) is rejected with no file access of any kind. Only after every required argument is present and every argument shape is valid, the overlap pre-check (`paths_overlap`, the same exit status and states) may make filesystem **metadata** calls, solely to detect overlapping paths and aliases: resolve symlinks in the supplied paths (`lstat` and `readlink` of path components) and compare the key and the manifest or output path as the same existing file (`stat` and a same-file comparison). It performs no open, no read of file content, no enumeration of directory contents and no write, and it is not a general exception for stage-1 file access (post-freeze clarification of 17 November 2026, see the note at the head of this document).
2. Manifest file read and structure. Unreadable, unsafe, oversized or malformed: `integrity_invalid`; `authenticity`, `expectations`, `freshness` are not evaluated. **A malformed manifest can never receive a successful integrity, authenticity or freshness result.**
3. Key file and authenticity. Any failure: `authenticity_invalid`; `integrity_not_evaluated` (the set is not checked against an unauthenticated manifest); `expectations_not_evaluated`; `freshness_not_evaluated`. **An invalid HMAC can never receive a successful authenticity result, and no expected-hash match is reported for it.**
4. Expectations: `expectations_met` or `expectations_not_met`.
5. Set integrity (runs when authenticity is valid, even if expectations were not met, so one run reports every failure of those stages): `integrity_valid` or `integrity_invalid`.
6. Freshness, evaluated only when the manifest parsed **and** authenticity is valid: `freshness_match` or `freshness_mismatch` if an expected hash was supplied, otherwise `freshness_not_evaluated`.

**Combinations that must hold** (examples; the tests of section 11 cover each row):

| Situation | integrity | authenticity | expectations | freshness | exit |
|---|---|---|---|---|---|
| All good, no expected hash | valid | valid | met | not_evaluated | 0 |
| All good, expected hash equal | valid | valid | met | match | 0 |
| All good, expected hash different | valid | valid | met | mismatch | 1 |
| Malformed manifest, expected hash supplied | invalid | not_evaluated | not_evaluated | not_evaluated | 1 |
| Parsed, MAC invalid, expected hash equals computed hash | not_evaluated | invalid | not_evaluated | not_evaluated | 1 |
| Authentic, one file altered | invalid | valid | met | not_evaluated or match or mismatch per hash | 1 |
| Authentic, declared installation differs from the expected UUID | valid or invalid per the set | valid | not_met | per hash | 1 |
| Key bound to a different installation than the manifest declares | not_evaluated | invalid | not_evaluated | not_evaluated | 1 |
| Missing required trust input | not_evaluated | not_evaluated | not_evaluated | not_evaluated | 2 |

Exit status for `verify`: `0` only when `integrity_valid`, `authenticity_valid` and `expectations_met`, and `freshness` is not `freshness_mismatch`; `1` for any other verification outcome; `2` for usage or trust-input errors. **A supplied expected manifest hash that does not match always fails (`freshness_mismatch`, exit 1), with or without `--require-freshness`.** `--require-freshness` controls only whether an expected hash must be supplied (without one it is a usage error, exit 2); it can never turn a supplied mismatch into a pass, and when given, `freshness` other than `freshness_match` also adds the reason `freshness_required_not_established`. `freshness_not_evaluated` with no hash and no `--require-freshness` does not change the exit status and the output still says so.

The prose, output schema (section 7.3), exit statuses, reason codes (section 7.3), acceptance criteria and tests (section 11) all use exactly these names.

## 3. Requirement and gate mapping, baseline and set definition

### 3.1 Requirement and gate mapping

| Item | Relationship |
|---|---|
| MVP-05 (Gate 11) | Contributes to "restore ... from protected backups: DB, exact originals, configuration, migration/model manifests ... and test failed/missing/tampered recovery inputs" from `docs/MVP_ACCEPTANCE.md`. Partial contribution only (the exclusions of section 0 apply); MVP-05 stays "planned / full acceptance not evidenced". |
| PLATFORM-03 | Contributes to "independent key/source/full-host recovery evidence" by defining and testing set verification; stays partial. |
| DOC-X02 (Gate 6) | **Enabler only.** A verified older manifest can list objects that were later forgotten (section 9.4). This slice does not reconcile forgetting; DOC-X02 stays open. |
| OPS-09 / PLATFORM-02 / OPS-10 | **Enablers only.** No backup-freshness observation, no RPO/RTO target, no measured objective is introduced. |

No register row, status, count, priority or acceptance criterion changes. This spec adds no requirement.

### 3.2 Existing baseline and what is reused

| Existing | Reuse in this slice |
|---|---|
| Spec 033 authenticated manifests: stdlib HMAC-SHA256, full tags, `secrets` key generation, domain-separated keyed fingerprint and MAC, constant-time comparison, fingerprint supplied independently | Same pattern and primitives, under a **new key purpose and new domains**. The Work key and Work modules are not reused or changed. |
| Spec 034 checkpoint rule: an expected manifest hash is an external input, never read from the candidate file | Same rule for the optional expected manifest hash. |
| `app/work_suppression_file.py` protected file handling (no-follow, single-link, owner-only, bounded, exclusive create, fsync of file and parent) and canonical JSON (`sort_keys`, compact separators, `allow_nan=False`), duplicate-key rejection | Same behaviour is required. Whether code is shared or re-implemented is a plan decision constrained by "Work behaviour is unchanged" (`plan.md`). |
| Spec 050 archive layout (`.archive.json` marker, `.archive.lock`, objects `<32 hex>-v<n>.original`, entry cap 8192 including marker and lock, 128 KiB per object, 64 MiB root) | Defines the archive members a set may contain. |
| `operations.inventory` package metadata | Source of the declared application and package version record. |
| `scripts/test-db-restore.sh` (`pg_dump --format=custom` in the `postgres:17` CI service container; restore into a second database) | The CI drill extends this script. |

**Correction to the proposed scope.** The assignment lists an "installation manifest from Spec 060" as a set member. No such product artifact exists. The spec 060 `BUTLER_INSTALLATION_RESTORE_MANIFEST_FILE` is a temporary file written by the test harness (`scripts/installation-restore-fixtures.py`); the installation UUID lives in the database (`installation_config.installation_id`) and in the dump. This spec therefore carries the installation identity as a **declared field in the manifest** (section 3.5), not as a file, and the fixture file is never a set member.

### 3.3 Permitted set contents

A set is a single directory (`SET`) containing exactly:

| Member | Path in `SET` | Rule |
|---|---|---|
| Database dump | `database.dump` | Required. One regular file, intended to be `pg_dump --format=custom` output. The tool treats it as opaque bytes. |
| Archive marker | `archive/.archive.json` | Present if and only if the manifest declares an archive. |
| Archive lock file | `archive/.archive.lock` | Present if and only if the archive is declared. |
| Archive objects | `archive/<32 hex>-v<n>.original` | Zero or more, individually enumerated in the manifest. |

Everything else is **declared metadata inside the manifest body**, not a file: the declared installation identity, schema manifest, application and package version manifest, optional model digest declaration, and Work hash references (section 4). The manifest and the key live **outside** `SET`.

**Archive field.** The `archive` field of the manifest stays optional in the format (`present: false` or `present: true`). A real recovery procedure may require the archive whenever the deployment has provisioned one; that requirement is enforced by the independently supplied expectation `--expect-archive` (section 5), not by the manifest.

Explicitly not members: the Work suppression manifest and checkpoint files (referenced by hash only), credentials, passwords, tokens, model weights, `.env` or host configuration, document keys, WAL, exports and the spec 060 harness manifest. Their presence in `SET` is `set_member_unexpected`.

### 3.4 Closed-set semantics and filesystem rules

`verify` and `generate` enumerate `SET` under the rules below, which are classified in section 3.6 as security invariants, supported-filesystem assumptions, informational checks and compatibility limits. Any violation stops with a closed reason code (section 7.3); the first violation in a fixed order is reported, plus a count of further violations only (never names outside the allowlist).

1. **Descriptor-relative enumeration.** `SET` and `archive/` are opened without following symlinks (`O_NOFOLLOW`, `O_DIRECTORY`) and read through directory descriptors; names are read once. Entries are processed in ascending order of their raw byte names, independent of filesystem order, locale and case.
2. **Name allowlist.** A path must match one of the permitted patterns of section 3.3 exactly. Object names match `[a-f0-9]{32}-v[1-9][0-9]{0,8}\.original`. Anything else (including `.pending-*` temporaries, editor backups, case variants and Unicode look-alikes) is unexpected, with the specific handling of pending objects in section 3.7.
3. **Path normalization.** Manifest member paths are relative, use `/` only, contain no empty, `.` or `..` segment, no NUL or backslash, are at most 64 bytes per segment and 2 segments deep, and must equal the allowlisted form byte for byte (no normalization is performed, so there is exactly one spelling). Absolute paths and traversal are rejected at manifest parse time, before any filesystem access.
4. **Types and links.** Only regular files and the single `archive` directory are permitted. Symlinks, hard-linked files (`st_nlink != 1`), sockets, FIFOs, devices and nested directories are rejected. The type is determined with `fstat` on the opened descriptor, not `lstat` of a path.
5. **Modes (mandatory).** Every member, the two directories (`SET` and `archive/`) and the manifest file must have **no group or other read permission and no group or other write permission** (`set_member_unsafe_mode` for members and directories, `manifest_file_unsafe` for the manifest). The key file must have no group or other permission bits at all (`key_file_unsafe`). These are mandatory failures; no informational note substitutes for them. Execute (search) bits on directories are not evaluated. The tool never changes modes. Section 3.6.1 states what these checks do and do not protect.
6. **Closed world.** The enumerated names must equal the manifest member list exactly: a member in the manifest but absent is `set_member_missing`; a name present but not in the manifest is `set_member_unexpected`; an unexpected directory is `set_directory_unexpected`. Duplicate member names or names differing only by case are `set_enumeration_ambiguous`.
7. **Bounds.** Section 3.8 defines every limit with its provenance. Exceeding one is `set_entry_limit_exceeded` or `set_size_limit_exceeded`, decided from `fstat` or entry counts **before** any hashing of that member.
8. **Single read per member.** Each member is opened once, `fstat`ed, hashed in a streaming loop with a fixed 1 MiB buffer reading at most the declared size plus one byte, and `fstat`ed again. A change of size, inode or modification time, or a read longer than declared, is `set_changed_during_read`. Memory use is constant regardless of dump size.
9. **No content interpretation.** The dump is never parsed. Only the archive marker (at most 256 bytes) is parsed, to compare its `root_id` with the declared `archive.root_id` (`archive_marker_mismatch`).

### 3.5 What the declared fields do and do not prove

`verify` has no database connection and does not parse the dump. Therefore:

- The **installation identity** and the **schema head and chain** are *operator declarations authenticated by the key* (owner decision O7). `verify` compares them with independently supplied expected values and for internal consistency. **The installation UUID does not prove that the supplied database dump originated from that installation**, nor that the dump is at the declared schema head. Database binding or restore-time identity verification is deferred to a later restore specification.
- The CI drill produces *test evidence* that a particular synthetic dump restores at the declared head. That evidence belongs to the drill (section 11.8), not to `verify`.
- The application and package version manifest is declared and authenticated only. It is never compared with the verifier's environment and is not a compatibility claim.
- The model digest declaration refers to no file in the set and is not checked against any model store.
- The Work hash references are opaque authenticated pass-throughs; the referenced files are not in the set and are not checked.

### 3.6 Security invariants, filesystem assumptions, informational checks, compatibility

**Class 1: mandatory security and integrity invariants** (never relaxed for convenience or because a storage medium cannot provide them; failing one fails the operation):

1. Directory and file opens never follow symlinks; members are regular files; special files, nested directories and traversal are rejected (section 3.4 rules 1 to 4).
2. A member must have exactly one hard link (`st_nlink == 1`). Another name for the same inode could alter verified bytes without touching the verified path.
3. Members, the two directories and the manifest file must have **no group or other read or write permission** (`set_member_unsafe_mode` for set members and directories, `manifest_file_unsafe` for the manifest). Write permission would let others alter what was verified, undermining even the point-in-time observation; read permission would let other local users read the set and the identifiers in the manifest (section 3.6.1).
4. The key file must be owner-only (no group or other permission bits at all), a single link, regular and bounded (`key_file_unsafe`). The manifest file must be a single-link regular file.
5. The set is a closed set (section 3.4 rule 6), sizes and SHA-256 are verified, and a member that changes while being read is a failure.
6. The verifier never writes inside `SET` and the generator never overwrites an existing file (section 9.1).

**Class 2: supported filesystem assumptions.** Verification and generation are specified for a **local POSIX filesystem on Linux** that provides all of: `O_NOFOLLOW` and `O_DIRECTORY` opens, directory-descriptor-relative operations, trustworthy `fstat` results for type, mode, link count, size, inode and modification time, `fsync` on files and on directories, and, for generation only, a no-replace atomic publication primitive (hard link creation that fails if the target exists, or a rename with a no-replace flag). The tool cannot prove a filesystem honours these; it detects a missing capability by the failure of the operation and then fails closed. Only the environment in which the future tests run is exercised; behaviour on any other filesystem is **unverified**, and this specification claims no universal portability.

**Class 3: informational checks** (never failures, never a protection claim, and never a substitute for a Class 1 failure):

- stale temporaries in the output directory: note `stale_temporary_present` (section 7.3.1). This is the only informational note. There is no permission note: every permission problem is a mandatory failure.

**Class 4: compatibility limitations and operational consequences.**

- Sets stored on FAT or exFAT, many SMB or NFS mounts, some USB filesystems and Windows hosts may report modes, link counts or inodes that do not satisfy Class 1, or may lack hard links, directory `fsync` or a no-replace primitive. On such media `verify` fails closed (`set_member_unsafe_mode`, `set_member_hardlinked` or `filesystem_unsupported`) and `generate` reports `filesystem_unsupported` with `publication: not_published`. The tool never falls back to a weaker primitive, never relaxes an invariant and never overwrites.
- The operator's consequence is to **copy the set onto a supported local filesystem** and then verify the copy. That copy is itself a new unverified artifact: the manifest's hashes are how the copy is checked, not the medium's metadata.
- Sets assembled by hard-linking from hard-link-based snapshots (for example `rsync --link-dest` trees) fail `set_member_hardlinked` and must be copied, not linked, into `SET`.
- Sets that arrive with group or other read or write bits (typical after copying through a network share or removable medium, or with a permissive umask) **fail** `set_member_unsafe_mode` or `manifest_file_unsafe`. The operator must copy the set to a supported local filesystem and set owner-only modes deliberately; the tool never repairs modes, so the failing copy stays failing until the operator changes it. A medium that cannot report trustworthy modes fails closed.

### 3.6.1 Integrity, confidentiality, filesystem assumptions and compatibility (permissions)

These four concerns are kept apart, and each permission rule is classified by which one it serves. Every rule below is a **mandatory failure**, not a warning.

| Concern | What this specification provides | Permission rule |
|---|---|---|
| **Integrity protection** | Detects alteration of a set against its authenticated manifest, and refuses a set that other local users could modify. | Group or other **write** on set members, `SET`, `archive/` or the manifest fails. Hard-linked members fail. |
| **Confidentiality protection** | A **local permission guard only**: a set or manifest that other local users could read (group or other **read**) fails verification and generation, so a set is not silently handled with permissive modes on this host. **No encryption** (out of scope, section 9.2), **no protection once a copy leaves this filesystem**, and no protection against a user who can already act as the owner or as root. A recovery set may contain sensitive household data (the dump, document originals) and the manifest names document identifiers (section 9.4). | Group or other **read** on set members, `SET`, `archive/` or the manifest fails (`set_member_unsafe_mode`, `manifest_file_unsafe`). The **key file** must have no group or other bits at all (`key_file_unsafe`), because it holds the secret. |
| **Supported filesystem assumptions** | Local POSIX on Linux (section 3.6 Class 2); modes and link counts must be trustworthy. | A medium that cannot report them fails closed; the tool does not guess. |
| **Operational compatibility** | A copy through media that rewrites modes may produce read or write bits for group or other. | Such a copy fails until the operator copies it to a supported local filesystem and sets modes deliberately; the tool never repairs modes. |

**No informational note implies confidentiality protection or substitutes for a mandatory failure.** The only note (`stale_temporary_present`) concerns generation temporaries. A passing permission check means only that, at the moment of the check, no group or other read or write bit was set on the checked objects; it is not a statement that the data is confidential, encrypted or protected elsewhere.

### 3.7 Archive quiescence and pending objects

The adapter writes archive objects through `.pending-*` temporaries, so a live archive can be observed mid-write. A changing archive must never be treated as a stable closed set.

- **Precondition (operator, not enforced).** The archive must be quiesced (no archive writer active) while a set is assembled and while `generate` runs. The tool does not take the archive lock and does not modify the archive. It cannot prove quiescence and only detects observable change.
- **Pending objects refuse both operations.** If any entry matching the adapter's pending pattern (`.pending-*`) is present in `archive/`, `generate` and `verify` fail with `archive_pending_objects_present`. `generate` publishes nothing (`publication: not_published`). No pending object is silently omitted, hashed or accepted as unexpected-but-ignored.
- **Change detection during generation.** `generate` enumerates the archive twice (before hashing and after hashing all members) and compares names, sizes, inodes and modification times. Any difference, or any pending object appearing between the passes, is `archive_changed_during_generation` and nothing is published.
- **Restricted claim.** A passing generation states only that no change was observed in those two passes. It does not state that the archive was quiescent or consistent with the database dump (that consistency is the operator's procedure, see `docs/DOCUMENT_ARCHIVE.md`: a consistent DB plus root backup).

### 3.8 Numeric limits, provenance and status

Six limits (entries, object size, archive payload, key file, manifest, read buffer) are **approved provisionally by the owner (O8)**. The dump size ceiling is **not approved**. None of these is validated operational capacity. They are classified honestly by provenance:

| Limit | Value | Class | Provenance and limitation |
|---|---|---|---|
| Archive entries (marker + lock + objects) | 8192; set members at most 8193 (plus the dump) | Existing-code-derived | `document_archive.MAX_ENTRIES`; the adapter counts objects plus marker and lock inside 8192. |
| Archive object size | 131072 bytes | Existing-code-derived | `document_archive.MAX_OBJECT`. |
| Archive payload total | 64 MiB | Existing-code-derived | `document_archive.MAX_BYTES`. |
| Key file size | 2048 bytes | Existing-code-derived | Same bound as the Work key file (`max_bytes=2048`). |
| Manifest size | 4 MiB | Provisional engineering limit | No existing code defines it. Estimated manifest at the entry cap is about 1.4 to 1.6 MB, so 4 MiB leaves headroom. |
| Read buffer | 1 MiB | Provisional engineering limit | Streaming bound only; not a requirement. |
| Dump size ceiling | 64 GiB placeholder | **Provisional engineering placeholder; not approved** | See below. **Not an approved operational capacity.** |

**Dump ceiling: provisional placeholder, not approved.** The owner has not approved 64 GiB as a fixed operational capacity limit, and **the real operational ceiling is deferred to measured resource testing and a separate owner decision.** The value remains in this document only as a labelled placeholder so that the limit-handling behaviour can be specified:

- *Rationale:* bound the worst-case work of one run (time grows linearly with bytes hashed; memory stays constant) and reject a runaway or wrong file before hashing. It says nothing about the size of any real database or about recovery capacity.
- *Resource bounds:* constant memory (1 MiB buffer), one pass, time linear in dump size.
- *Failure behaviour:* a dump whose `fstat` size exceeds the ceiling fails with `set_size_limit_exceeded` before any hashing; nothing is published by `generate`.
- *Test limits (synthetic-only implementation):* every limit of this section must be **overridable through an internal, test-only injection point** (a parameter of the verification and generation functions), so that limit handling is exercised with **small synthetic fixtures**. The injection point is not reachable from the command line, environment or any configuration file, and is not an operator setting. **No test requires 64 GiB of data.** A passing limit test shows only that the logic reacts to the injected limit, not that any real dump of any size is handled.
- *Real use:* until the real ceiling is decided from measured testing, the placeholder must not be presented, documented or relied on as validated capacity, and no real set may be treated as supported by it.

**Three classes kept distinct:** existing-code-derived limits (above), provisional engineering limits (manifest, buffer), the unapproved dump-ceiling placeholder, and **measured operational capacity (none exists)**. Unconfirmed or provisional thresholds, and every synthetic result against them, **do not count as passing recovery evidence**.

## 4. Manifest format (version 1)

### 4.1 Representation

- UTF-8 JSON, canonical form identical to the existing Work manifests: object keys sorted, separators `,` and `:` with no insignificant whitespace, `allow_nan=False`, no floating-point numbers (integers only), `ensure_ascii` escaping. The file stores exactly the canonical bytes with no trailing newline.
- The parser **rejects duplicate keys at every depth**, unknown fields at every depth (closed schema, `extra=forbid`), a wrong or missing `schema_version`, non-canonical input (re-serializing the parsed value must reproduce the input bytes exactly), integers outside the declared ranges, strings outside the declared patterns, and any size above the manifest limit (`manifest_too_large`).
- A manifest with an unknown `schema_version` is `manifest_schema_unsupported`; there is no best-effort parsing.
- **There is no free-text field** (owner decision): no operator note, comment, description or label. Every string is an identifier, digest, version, tag, timestamp or fixed vocabulary value constrained by a pattern, so the manifest has no unbounded channel that could leak information or introduce parsing ambiguity.

### 4.2 Envelope, authentication and the keyed fingerprint

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
- **Keyed fingerprint.** As in spec 033, the fingerprint is a **keyed tag, not an unkeyed hash**: `key_fingerprint = HMAC-SHA256(key material, FINGERPRINT_DOMAIN || canonical(public identity fields))`, where the public identity fields are key id, purpose, installation id and creation time, and the key material itself is excluded from the serialized input but is the HMAC key. It therefore binds the secret: a different secret with identical public fields yields a different fingerprint. It reveals nothing about the secret, and anyone holding the secret can compute it, so it identifies a key to someone who holds it and is useful to a verifier only because the expected value is pinned independently. It is never an unkeyed digest of public fields, and key material never appears in the manifest, output or logs.
- `MAC_DOMAIN = b"butler.installation-recovery-set-mac.v1\n"`; `FINGERPRINT_DOMAIN = b"butler.installation-recovery-set-key-fingerprint.v1\n"`. Both are distinct from each other and from every Work domain (`butler.synthetic.work-recovery-key-fingerprint.v1`, `butler.synthetic.work-suppression-auth.v2`).
- **Manifest hash** (the freshness handle): `manifest_hash = SHA-256(HASH_DOMAIN || canonical(payload))` with `HASH_DOMAIN = b"butler.installation-recovery-set-manifest-hash.v1\n"`. It covers the key references and the entire body and excludes the MAC, so the hash can be retained independently of the key. Because it excludes the MAC, **it proves nothing about authenticity**; that is why freshness is evaluated only after authenticity is valid (section 2.5).
- The payload embeds `key_id` and `key_fingerprint` so a MAC cannot be transplanted to a different key claim.

### 4.3 Body

| Field | Content | Notes |
|---|---|---|
| `set_id` | UUID | Random per generation unless supplied for tests. |
| `created_at` | aware UTC timestamp | Application clock; subject to the clock limitation of spec 073 section 1.4.1 and informational only. It is never used to decide freshness. |
| `generator` | `{ "tool_version": "<string>" }` | Fixed pattern, at most 32 characters. |
| `installation` | `{ "installation_id": "<uuid>" }` | **Declared** (section 3.5). |
| `schema` | `{ "head": "<revision id>", "revisions": ["<id>", ...] }` | Ordered oldest to newest; `head` equals the last element; derived by the generator from the migration scripts of its own code, offline. |
| `application` | `{ "api_version": "...", "python_version": "...", "packages": { "fastapi": "...\|null", "sqlalchemy": ..., "psycopg": ..., "pydantic": ... } }` | Same four packages as `operations.inventory`; values limited to the existing safe-version pattern or `null`. |
| `model` | `{ "declared": false }` or `{ "declared": true, "tag": "<tag>", "digest": "<64 hex>" }` | Tag and digest follow the existing local-model validators in `app/config.py`. Declaration only. |
| `work_references` | `{ "suppression_manifest_sha256": "<64 hex>\|null", "source_checkpoint_sha256": "<64 hex>\|null" }` | Hash references only (owner decision O2), copied by the operator from the retained spec 034 checkpoint records. |
| `archive` | `{ "present": false }` or `{ "present": true, "root_id": "<uuid>", "object_count": <int> }` | Optional in the format. `root_id` is read by the generator from the marker. |
| `members` | ordered list of `{ "path": "...", "kind": "dump\|archive_marker\|archive_lock\|archive_object", "size": <int>, "sha256": "<64 hex>" }` | Sorted by raw path bytes; this order is part of the canonical form. |

The body contains metadata and cryptographic references only: no file content, no document text, no personal data, no key material, no host path, no hostname or user name, no timing values, no free text.

### 4.4 Determinism

Given identical member bytes, identical operator declarations (installation id, model declaration, Work references, archive expectation), the same key, the same `created_at` and `set_id`, `generate` produces byte-identical output regardless of enumeration order, locale or platform. Timing is not stored in the manifest; it appears only in command output (section 7.3).

## 5. External trust inputs and provenance

The manifest must not establish its own trust. `verify` accepts trust inputs **only as explicit command-line arguments or the explicit key file argument**. There is no environment-variable, configuration-file, default-path or "same directory" fallback, and no value is ever read from the manifest, the set, a database, an audit event, a log or a previous tool output to satisfy a check.

### 5.1 Inputs

| Input | Argument | Required | What it is checked against | Required provenance |
|---|---|---|---|---|
| Expected key fingerprint | `--expected-key-fingerprint HEX64` | Yes | the keyed fingerprint recomputed from the key file, the payload's `key_fingerprint`, and the MAC | Recorded at key generation in a record kept separately from the key file, the set, the manifest and the database (as in spec 033). |
| Recovery key file | `--recovery-key PATH` | Yes | namespace, installation binding, fingerprint | Protected key custody (section 6); never inside `SET`. |
| Expected installation UUID | `--expected-installation-id UUID` | Yes | the manifest's declared installation id (an expectations check). The key file's installation binding is separately checked against the manifest's declared id as part of authenticity | An independently retained record of the installation identity, **not** read from the dump, the database or the manifest. |
| Expected schema head | `--expected-schema-head REVISION` | Yes | the manifest's declared `schema.head` | The head the recovery operator intends to restore, chosen independently. An older head than the verifier's code is allowed when restoring an older backup. |
| Expected archive presence | `--expect-archive present\|absent` | Yes | the manifest's declared `archive.present`, and through the closed set the actual set | The operator's independent knowledge of whether the deployment provisioned an archive. **Never derived from the manifest.** |
| Expected manifest hash | `--expected-manifest-hash HEX64` | Optional | the computed `manifest_hash`, for freshness only (section 2.3) | An independently governed and retained record. |

`--expect-archive` is compared with the declared value and the actual set: expectation versus declared mismatch is `archive_expectation_mismatch`; declared versus actual mismatch is the closed-set error (`set_member_missing` or `set_directory_unexpected`). A real recovery procedure may require `present` whenever the deployment has provisioned an archive. **`--expect-archive present|absent` is mandatory on every `generate` and `verify` invocation** (owner decision): the operator must state the expectation explicitly, there is no default, omission is `trust_input_missing` (exit 2, before any file access), and the verifier compares the independently supplied expectation with the actual set.

A **schema policy** permitting more than one head is deliberately not defined; exact match only. Permitting upgrades is a restore-time decision.

### 5.2 Provenance requirements and limits

- Each expected value must come from a record retained independently of the set storage, of the key custody and of the verifier host, so that compromising one does not let an attacker supply all of them. The tool cannot verify independence; it can only refuse to take values from the candidate artifacts.
- A supplied expected manifest hash proves only that the supplied manifest equals that hash. It shows the manifest is the latest only if the *source* of the hash is independently governed and retained (who records it, when, where, and how it is updated after each backup). That governance is a deferred owner decision outside this slice (O5).
- A deliberately supplied older hash matches an older manifest. The tool cannot detect that choice.
- A supplied expected manifest hash that does not match always fails (`freshness_mismatch`, exit 1), with or without `--require-freshness`. `--require-freshness` controls only whether an expected hash must be supplied: given without `--expected-manifest-hash` it is a usage error (`freshness_requested_without_expected_hash`, exit 2, before any file access). It never allows a supplied mismatch to pass.

## 6. Trust anchor and key custody

### 6.1 Approved direction (O1a) and deferred governance (O1b)

**O1a, owner-approved:** use a dedicated recovery-specific offline HMAC key, separate from every Work key, application secret, database credential and document key. HMAC-SHA256 under that key authenticates the manifest.

**O1b, deferred, undecided:** the real-world key holder, custody arrangement, storage location, access procedure, backup and loss-recovery procedure. This specification names none of them and assumes none is approved. **The repository establishes no reviewed encrypted/off-site key policy**; the Work documentation refers to one by name, but none exists in the repository, and this specification does not create or imply one. This slice generates, provisions, stores and uses **no real key**; a synthetic key may be created by a test helper in future synthetic engineering tests only.

### 6.2 Key file and namespace separation

- The key file is JSON bounded at 2 KiB with `schema_version`, `purpose: "installation_recovery_set"`, `key_id`, `installation_id`, `created_at` and 32 bytes of material as 64 hex characters held as a masked secret type. It is read with the protected-file rules (regular, single link, owner-only, no-follow, bounded).
- `purpose` and the installation binding give namespace separation: a Work key file, a database credential file or any file with another `purpose` fails with `key_namespace_mismatch` and is never interpreted as recovery material; a key bound to installation A used with a manifest that declares installation B fails with `key_installation_mismatch` (authenticity). Whether the declared installation is the one the operator expected is a separate comparison with `--expected-installation-id` (expectations, `installation_mismatch`).
- Fingerprint and MAC domains are distinct from each other and from every Work domain. Nothing in this slice reads, writes or changes Work keys or Work key files.

### 6.3 Secret handling

Key material never appears in manifests, command output, error messages, log lines, test artifacts, exception text or tracebacks. It is never accepted as an argument or environment value. The command catches all exceptions at its boundary and prints only a reason code. Tests assert absence of the material (and of its hex, base64 and repr forms) across stdout, stderr, files written and captured logs, including for crashing inputs.

### 6.4 HMAC limitation (O6, approved: HMAC for this specification)

**Every holder of the verification secret can also create a valid manifest.** HMAC is symmetric, so there is no separation between "can verify" and "can forge", no non-repudiation, and a compromised verifier host that holds the key can forge a manifest for a malicious set and then verify it. This specification **claims no separation of duties and no public-key verification**. It matches spec 033, adds no dependency (the project has no asymmetric signing library) and is simple to test offline. Asymmetric signatures are revisited only if a future governance decision requires a verify-only party or separation of duties; that is not decided here.

### 6.5 Generation-host trust boundary and what the HMAC attests

`generate` requires the HMAC secret to be present on the host that runs it. **The generation host is therefore a trust boundary**: whoever controls it can attest anything. "Offline verification" means `verify` needs no database or network; it does not mean a manifest can be generated without the secret being present on the generation host. The HMAC attests exactly one thing: **the manifest bytes were authenticated by a holder of the key at generation time.** It does not prove that the database dump is genuine, complete, current or recoverable, that the set was consistent when the dump and archive were taken, or that the generation host was uncompromised.

### 6.6 Custody responsibilities (holder and location deferred, O1b)

Any future arrangement must satisfy at least:

1. The key and its fingerprint record are held **separately from each other** and separately from the sets they authenticate.
2. There is an accountable, recorded owner of the key and a defined second person or mechanism able to recover it.
3. The key is protected at rest by a mechanism independent of the production host and of the backup storage.
4. Access is limited, recorded and reviewable; use of the key for generation is deliberate, not automatic.
5. Recovery of the key is itself rehearsed.
6. The expected-fingerprint record is retained with the same independence as the expected-hash record (section 5.2).

### 6.7 Rotation, replacement, loss and compromise (specification level)

| Event | Consequence | Not provided in this slice |
|---|---|---|
| Planned rotation | Create a new key and fingerprint record; new manifests use it. Old manifests verify only with their old key and fingerprint, which must be retained as long as those manifests are in use. | No rotation command, no key registry, no automatic re-signing. |
| Replacement | Equivalent to rotation after a lost or damaged key file when a copy exists. | No key escrow mechanism. |
| **Loss of the key** | Authenticity cannot be established for existing manifests. Integrity of a set against its manifest can still be checked, but proves nothing about origin. New manifests need a new key and a trusted way to re-attest existing sets. | No recovery of a lost key; no unsigned bypass flag. |
| **Compromise** | Every manifest authenticated under that key is untrusted, including old ones, and the holder could have forged any of them. Affected sets must be re-validated from known-good sources and re-attested under a new key with a new independently recorded fingerprint. | No revocation list or online status; a revoked key is identified only by the operator's records. |

## 7. Command interface, outputs, reason codes

The module and flag names are proposals; the observable contract (separate states, closed codes, exit statuses) is what matters.

### 7.1 Operations

`generate` (offline, no database, no network):

```
generate --set DIR --output MANIFEST_FILE --recovery-key KEY_FILE --expected-key-fingerprint HEX64
         --installation-id UUID --schema-head REVISION --expect-archive present|absent
         [--model-tag TAG --model-digest HEX64]
         [--work-suppression-manifest-sha256 HEX64] [--work-source-checkpoint-sha256 HEX64]
```

`generate` reads `SET` read-only, applies sections 3.4 and 3.7, writes only `MANIFEST_FILE`, and prints the new `manifest_hash`, key references, member count, byte total and elapsed milliseconds. It requires the same expected fingerprint as `verify` so a generator cannot silently use a different key, and `--expect-archive` so an archive cannot be silently omitted: a mismatch between the expectation and the set refuses generation (`archive_expectation_mismatch`). It requires the HMAC secret on the host (section 6.5) and is a trusted operator action over a set the operator has quiesced.

`verify` (offline, read-only, no database, no network):

```
verify --set DIR --manifest MANIFEST_FILE --recovery-key KEY_FILE
       --expected-key-fingerprint HEX64 --expected-installation-id UUID --expected-schema-head REVISION
       --expect-archive present|absent
       [--expected-manifest-hash HEX64] [--require-freshness]
```

`MANIFEST_FILE` and `KEY_FILE` must not be inside `SET`, nor inside each other's directory in a way that makes them set members (`paths_overlap`, exit 2). The pre-check that detects this is bounded by section 2.5 (metadata calls only, after every argument shape is valid).

### 7.2 Evaluation order

The order of section 2.5 governs. Within it:

1. Trust-input shape: every required input present and well-formed, including a mandatory `--expect-archive present|absent`; `--require-freshness` requires a hash.
2. Manifest file: protected read, size, parse and structure checks.
3. Key file: protected read, namespace, keyed fingerprint equals the expected fingerprint, the key file's installation binding equals the installation id declared in the manifest (`key_installation_mismatch`); payload key references; MAC. These set `authenticity`.
4. Expectations: the declared installation id equals the expected UUID; declared schema head equals the expected head; the declared chain is internally consistent (head last, no duplicates) and a prefix of the verifier's own migration chain (`schema_unknown_to_verifier` when the verifier does not know a declared revision, `schema_chain_inconsistent` otherwise); archive expectation equals declared presence.
5. Set integrity: sections 3.4 and 3.7.
6. Freshness: the optional hash comparison, only when parsed and authentic. It never changes `integrity`, `authenticity` or `expectations`.

### 7.3 Output and exit status

The command prints one JSON object with a closed key set; unknown or additional keys are never emitted. `verify` and `generate` share the keys below unless marked.

| Key | Meaning |
|---|---|
| `schema_version`, `operation` | `1`; `generate` or `verify` |
| `integrity`, `authenticity`, `expectations`, `freshness` | The enumerations of section 2.5 (`verify`). For `generate` these describe the checks the generator performed on the freshly read set and the key: `freshness` is always `freshness_not_evaluated`. |
| `reasons` | Ordered list of closed reason codes (empty if and only if there was no failure) |
| `notes` | Always present. Informational notes, never failure reasons (section 7.3.1) |
| `manifest_hash`, `key_id`, `key_fingerprint` | Public references, when computed |
| `member_count`, `member_bytes` | Integers, when the set was enumerated |
| `verified_references` | `verify` only. Present **only** when `integrity` is `integrity_valid`, `authenticity` is `authenticity_valid` and `expectations` is `expectations_met`; otherwise absent. Object with `set_id`, `manifest_hash`, `dump_sha256` and `members_digest` (SHA-256 over the canonical member list). Public identifiers for a future restore specification to bind to. They are a point-in-time observation, **not** a guarantee that the bytes are unchanged (section 8). |
| `elapsed_ms` | Tool-measured duration of this run; informational only; **not** a recovery-time measurement |
| `point_in_time` | Always `true` |
| `restore_performed`, `recovery_complete` | Always `false` |
| `freshness_note` | Fixed string present only with `freshness_match`: `matches_supplied_expected_hash_only` |
| `publication` | `generate` only: `not_published`, `published_durability_uncertain`, `published_durable` (section 9.1) |

Exit status for `verify`: section 2.5. Exit status for `generate`: `0` only when `publication` is `published_durable`; `1` for every other outcome, including `published_durability_uncertain`; `2` for usage or trust-input errors. Notes never change an exit status.

Reason codes (closed, stable; additions need a spec change):

| Group | Codes |
|---|---|
| Usage and trust inputs | `trust_input_missing`, `trust_input_malformed`, `freshness_requested_without_expected_hash`, `paths_overlap` |
| Key | `key_file_unsafe`, `key_file_malformed`, `key_namespace_mismatch`, `key_installation_mismatch`, `key_fingerprint_mismatch` |
| Manifest | `manifest_file_unsafe`, `manifest_too_large`, `manifest_malformed`, `manifest_duplicate_key`, `manifest_unknown_field`, `manifest_noncanonical`, `manifest_schema_unsupported`, `manifest_key_reference_mismatch`, `manifest_authentication_failed`, `manifest_path_unsafe` |
| Expectations | `installation_mismatch`, `schema_head_mismatch`, `schema_chain_inconsistent`, `schema_unknown_to_verifier`, `archive_expectation_mismatch` |
| Set | `set_member_missing`, `set_member_unexpected`, `set_directory_unexpected`, `set_path_unsafe`, `set_member_not_regular`, `set_member_symlink`, `set_member_hardlinked`, `set_member_unsafe_mode`, `set_member_size_mismatch`, `set_member_hash_mismatch`, `set_entry_limit_exceeded`, `set_size_limit_exceeded`, `set_enumeration_ambiguous`, `set_changed_during_read`, `archive_marker_mismatch`, `archive_pending_objects_present`, `archive_changed_during_generation` |
| Freshness | `freshness_expected_hash_mismatch` (an expected hash was supplied and differs), `freshness_required_not_established` (`--require-freshness` and the state is not `freshness_match`) |
| Filesystem and generation | `filesystem_unsupported`, `output_exists`, `output_unsafe`, `io_error`, `publication_durability_uncertain` |
| Internal | `internal_error` (no detail) |

#### 7.3.0 Reason-code definitions and state effects

Every reason code has exactly one meaning and one state effect. "Exit" is the exit status of the operation that reports it.

| Code | Meaning | State effect | Exit |
|---|---|---|---|
| `trust_input_missing`, `trust_input_malformed` | A required input (including `--expect-archive`) is absent or not well-formed. | all fields `*_not_evaluated` | 2 |
| `freshness_requested_without_expected_hash` | `--require-freshness` without `--expected-manifest-hash`. | all `*_not_evaluated` | 2 |
| `paths_overlap` | The manifest, key or output path lies inside `SET`, or the key and manifest overlap. | all `*_not_evaluated` | 2 |
| `key_file_unsafe`, `key_file_malformed` | The key file is not a protected, single-link, owner-only (no group or other permission bits at all), bounded regular file, or is not valid key JSON. | `authenticity_invalid` | 1 |
| `key_namespace_mismatch` | The key file's `purpose` is not `installation_recovery_set`. | `authenticity_invalid` | 1 |
| `key_fingerprint_mismatch` | The recomputed keyed fingerprint differs from the expected fingerprint. | `authenticity_invalid` | 1 |
| `key_installation_mismatch` | The key file's installation binding differs from the installation id declared in the manifest. | `authenticity_invalid` | 1 |
| `manifest_key_reference_mismatch` | The payload `key_id` or `key_fingerprint` differs from the key file's. | `authenticity_invalid` | 1 |
| `manifest_authentication_failed` | The MAC does not verify. | `authenticity_invalid` | 1 |
| `manifest_file_unsafe`, `manifest_too_large`, `manifest_malformed`, `manifest_duplicate_key`, `manifest_unknown_field`, `manifest_noncanonical`, `manifest_schema_unsupported`, `manifest_path_unsafe` | The manifest cannot be read safely (including **any group or other read or write permission on the manifest file**, `manifest_file_unsafe`) or fails structural validation. | `integrity_invalid`; later stages not evaluated | 1 |
| `installation_mismatch` | The manifest's declared installation id differs from `--expected-installation-id`. | `expectations_not_met` | 1 |
| `schema_head_mismatch`, `schema_chain_inconsistent`, `schema_unknown_to_verifier` | The declared head differs from `--expected-schema-head`; the declared chain is internally inconsistent; or the verifier does not know a declared revision. | `expectations_not_met` | 1 |
| `archive_expectation_mismatch` | `--expect-archive` differs from the manifest's declared `archive.present`. | `expectations_not_met` | 1 |
| `set_member_missing`, `set_member_unexpected`, `set_directory_unexpected`, `set_path_unsafe`, `set_member_not_regular`, `set_member_symlink`, `set_member_hardlinked`, `set_member_unsafe_mode`, `set_member_size_mismatch`, `set_member_hash_mismatch`, `set_enumeration_ambiguous`, `set_changed_during_read`, `archive_marker_mismatch` | The set contradicts the manifest or violates a closed-set or security invariant (section 3.4, 3.6), including **any group or other read or write permission** on a member, `SET` or `archive/` (`set_member_unsafe_mode`). | `integrity_invalid` | 1 |
| `set_entry_limit_exceeded`, `set_size_limit_exceeded` | A member count or a size exceeds a limit of section 3.8 (decided before hashing). | `integrity_invalid` | 1 |
| `archive_pending_objects_present` | A `.pending-*` object is present in `archive/` (section 3.7). | `integrity_invalid` (`verify`); no publication (`generate`) | 1 |
| `archive_changed_during_generation` | The two archive enumeration passes of `generate` differ. | no publication | 1 |
| `freshness_expected_hash_mismatch` | An expected hash was supplied, the manifest parsed and is authentic, and the computed hash differs. | `freshness_mismatch` | 1 |
| `freshness_required_not_established` | `--require-freshness` was given and `freshness` is not `freshness_match`. Always accompanies another reason. | none | 1 |
| `filesystem_unsupported` | A required filesystem capability is unavailable (section 3.6 Class 2, 9.1). | `generate`: `publication: not_published` | 1 |
| `output_exists` | A file already exists at the output path. | `publication: not_published` | 1 |
| `output_unsafe` | The output path is a symlink, a directory, inside `SET`, or its parent is group- or other-writable. | `publication: not_published` | 1 |
| `io_error` | An I/O error occurred. | `generate`: `publication: not_published` before publication; `verify`: `integrity_invalid` if it prevented reading the set | 1 |
| `publication_durability_uncertain` | The final manifest was published but directory durability could not be confirmed (G5). | `publication: published_durability_uncertain` | 1 |
| `internal_error` | An unexpected error; no detail is printed. | all unevaluated stages stay `*_not_evaluated`; `generate`: `not_published` unless published | 1 |

#### 7.3.1 Informational notes (separate from failure reasons)

`reasons` lists failures and is empty if and only if the operation had no failure. `notes` is a separate, bounded, informational list:

- **Schema:** a JSON array of strings, each from a closed vocabulary, at most as many entries as the vocabulary has (currently 1), no duplicates, sorted ascending by byte value, never containing a path, name, count, value or free text. Additions need a spec change.
- **Vocabulary (version 1):** `stale_temporary_present` only. Meaning: while preparing `generate`, the output directory held at least one entry whose name starts with the tool's temporary prefix. Detection examines at most the first 64 entries in sorted order and reports only the fixed string. There is no note about permissions: group or other read or write permission is a mandatory failure (section 3.6), never a note.
- **Emission:** `generate` emits it when applicable. `verify` performs no such scan and always emits `"notes": []`.
- **On success and on failure:** notes may accompany a successful result (exit `0`, `reasons: []`) and an unsuccessful one. They never change `integrity`, `authenticity`, `expectations`, `freshness`, `reasons`, `publication` or the exit status.
- **Stale temporaries inside `SET`** are not notes: an unexpected file in `SET` is the failure `set_member_unexpected`.

Safe error handling: no exception text, no traceback, no path the operator supplied (only the closed code), no file content and no key material is printed. Member names are printed only if they match the allowlist. The tool never echoes a supplied expected value that failed to match; it states which check failed.

## 8. Verification-to-restore gap

A successful `verify` is a **point-in-time observation** of the bytes the tool read. A verified set can change after verification and before restoration (another process, a replaced medium, storage corruption, or an attacker with write access). This slice performs no restoration, so it **does not guarantee that a later restore consumes the bytes that were verified**, and a previous verification result alone must never be treated as that guarantee. The output states `point_in_time: true`, and tests demonstrate the limitation.

**Approved principle (for a later restore specification only):** a future restore procedure should operate on the **exact staged copy whose bytes were verified**, or an equivalently strong mechanism, and that later specification must require it. Options for that specification include (a) a combined verify-and-stage that copies members into a private staging directory while hashing them, so restore reads the staged, verified copy; (b) hash-while-restoring, so the restore stream is itself verified; (c) restoring from immutable or read-only media with write access removed between verification and restore. Re-verification immediately before restore narrows the window but does not by itself remove it.

**Spec 074 implements none of this:** no staging, no restoration, no database writes, no migration execution. To let a later specification bind to what was verified, `verify` exposes `verified_references` (section 7.3) only when integrity, authenticity and expectations all hold.

## 9. Atomic generation, failure semantics, scope boundaries

### 9.1 Observable guarantees for manifest publication

**Supported filesystem assumptions** are those of section 3.6 Class 2. Publication needs a **no-replace atomic primitive**: creating a hard link from the temporary file to the final name (which fails with `EEXIST` if the name exists), or a rename with a no-replace flag (`renameat2` with `RENAME_NOREPLACE` on Linux). A plain `rename` is **forbidden** because it replaces an existing file. If neither primitive is available (for example the filesystem returns `EPERM`, `ENOTSUP`, `EINVAL` or `EXDEV`), the tool fails with `filesystem_unsupported` and `publication: not_published`; it never falls back to a replacing rename, a copy, or a check-then-write sequence, and it makes no portability claim for such a filesystem.

**Publication stages.** A `generate` run passes through ordered stages, and the guarantees depend on where a failure occurs:

1. **Pre-publication:** reading the set, validating (including quiescence checks of section 3.7), serializing, creating and writing the temporary file, flushing the temporary file.
2. **Publication:** the single no-replace atomic step that makes the final name appear. It either happens completely or not at all.
3. **Post-publication, pre-durability:** the final name may already exist and be complete; the containing directory has not yet been confirmed durable.
4. **Durable:** directory durability (`fsync` of the containing directory, where applicable to the filesystem) was confirmed.

The command reports the stage outcome in the `publication` field: `not_published`, `published_durability_uncertain` or `published_durable`. Only `published_durable` is a success.

- **G1 No partial final manifest.** At every moment, including after any interruption (crash, kill, power loss, I/O error, out of space), the final manifest path either does not exist or contains a complete, valid manifest. Never a prefix, never a mix. G1 says nothing about whether a *complete* final file is durable (G5), and does not promise the final path is absent after a failure.
- **G2 No overwrite.** An existing file at the output path is never modified, truncated, replaced or removed. `generate` fails with `output_exists` and `publication: not_published`. There is no replace option.
- **G3 Temporary files.** Temporaries are created exclusively (never reusing a name), owner-only, in the output directory, with a recognizable prefix and a per-run random token. A run removes its own temporary on every failure it survives and after publication. A temporary that remains (killed run, or removal failure) is a **documented recoverable artifact**: never at the final name, never mistaken for a manifest, never deleted by a later run (which cannot prove it created it), and reported through the informational `stale_temporary_present` note, never as a failure reason. The operator may delete it after inspection. If a temporary exists because publication used a hard link and cleanup failed, it holds the same bytes as the final manifest.
- **G4 Atomic publication.** The final name appears in one step through the no-replace primitive above, with the temporary file fully written and flushed beforehand.
- **G5 Durability and the post-publication window.** The temporary file is flushed to stable storage before publication, and the containing directory is flushed after. Between publication and a confirmed directory flush, a complete final manifest **may exist while durability is uncertain**. If the directory flush fails or cannot be confirmed, `generate` **must** report failure (exit status 1), reason `publication_durability_uncertain` and `publication: published_durability_uncertain`, and **never** report `published_durable` or exit status 0. It must not state or imply that the final file is absent, and must not delete, rename or overwrite the possibly published file. Success (`published_durable`, exit 0) means only: the file was published and the directory flush was confirmed, on a filesystem and storage that honour `fsync`, which is outside the tool's control.
- **G6 Concurrent generation.** Two generators targeting the same output path: exactly one publishes; the other receives `output_exists`; neither leaves a partial file and neither corrupts the other's result. Generators targeting different outputs do not interfere. Concurrent *modification of the set* is not prevented, only detected (`set_changed_during_read`, `archive_changed_during_generation`).
- **G7 Failure semantics by stage.**
  - *Before publication:* any error while reading the set, validating, writing or flushing ends the run with the specific set code, `io_error` or `filesystem_unsupported`, exit status 1, `publication: not_published`, **no final manifest**, and best-effort removal of the run's own temporary (a remaining temporary is a G3 artifact).
  - *After publication, before durability confirmation:* G5 applies (`publication_durability_uncertain`, exit 1; a complete final manifest may exist).
  - The tool never reports success when any write, flush, publish or directory-flush step failed.
- **G8 Output path safety.** An output path that is a symlink, a directory, inside `SET`, or whose parent is writable by group or other is `output_unsafe`.
- **G9 Safe retry and operator recovery.** The tool never silently overwrites. After `publication_durability_uncertain`, or any failure whose outcome is unclear:
  1. A retry to the **same** output path fails with `output_exists` if the final file exists (G2); the tool does not distinguish an earlier uncertain publication from any other existing file and says nothing about its durability.
  2. The operator inspects the existing file by running `verify` with the independently supplied trust inputs; a complete file verifies like any other manifest (it carries no marker of the uncertainty). The operator may also compare its `manifest_hash` with the one the failed run printed (the failed run's output includes it, because it is computed before publication).
  3. If acceptable, the operator makes it durable by an action **outside the tool** (for example a filesystem sync by the operator, or copying it to storage whose durability they control); the tool offers no way to confirm that. Alternatively the operator moves the file aside themselves and runs `generate` to a new path or the same path.
  4. The tool provides no replace, force or cleanup option in this slice.

### 9.2 Scope boundaries

In scope: the offline `generate` and `verify` operations; read-only verification; deterministic manifest generation; integrity and authenticity checks; external expected-value inputs; synthetic tests and a CI drill using real `pg_dump` output; stable non-sensitive results.

Out of scope: database writes or migrations; runtime API, UI, worker or compose changes; restoration and staging; real keys, real NAS, production hosts or external infrastructure; encryption of backups or archives; backup scheduling, freshness services or any latest-manifest authority; DOC-X02 forgetting reconciliation and non-Work suppression exports; worker liveness or alerting; **approved-job and reminder-worker process-kill tests (owner decision O4: a later, separate specification)**; acceptance of RPO/RTO targets; clean-host claims; key-generation tooling and any provisioning workflow (O9).

### 9.3 Data-flow statement (constitution, principle I)

Nothing leaves the private environment. The tool opens no network connection and no database connection, runs offline on local files, and sends no content to any provider or model. The manifest is a local file whose handling is the operator's responsibility.

### 9.4 Security and privacy constraints

- **Data ownership.** The tool owns no data: the dump, archive and Work artifacts remain the authority; the manifest is evidence about files, never a source of truth for business records, never an approval or authority to restore, and never a second authority over forgetting decisions.
- **Metadata disclosure and retention (O2).** Archive object names encode a document UUID and revision, and sizes are recorded. **A manifest may therefore reveal document identifiers, existence or metadata**, and an old manifest keeps naming objects later forgotten and purged. This creates a privacy and retention consideration. The manifest must be handled as sensitive operational metadata under the same access control as backups. **The manifest must never become permission to restore forgotten material**: a manifest listing a forgotten object is valid evidence about an old set only, and forgetting reconciliation (DOC-X02) must still run on restored older data. The specification distinguishes four matters and **finalizes none of the retention durations or a universal retention policy**, which are deferred to a separate governance decision:
  1. *Manifest retention*: how long manifests are kept.
  2. *Backup and archive retention*: how long sets and archives are kept (existing documentation already says older backups can reintroduce forgotten data and are outside recall).
  3. *Independently retained expected-hash records*: hash-only records held for freshness comparison (section 5.2).
  4. *Forgetting and deletion reconciliation*: how forgotten identifiers are handled in retained manifests and restored data.
- **Least privilege.** The tool runs as an unprivileged user with read access to the set and key and write access to the output directory only. It does not need and must not use the runtime database role, the migration owner or any service credential.
- **Bounded resource use.** Constant memory (1 MiB buffer), bounded member count, bounded manifest and key size, one pass per member, no recursion, no network and no unbounded loops.

## 10. Owner decisions, deferrals and open questions

### 10.1 Recorded owner decisions (14 November 2026)

These record the **approved design direction** on which the frozen revision rests. None authorizes implementation.

| ID | Decision | Status |
|---|---|---|
| **O1a** | Use a dedicated recovery-specific offline HMAC key, separate from Work and application keys. | **Approved** |
| **O2 (content)** | Work suppression artifacts by hash only; archive objects individually hashed and enumerated; the manifest is never permission to restore forgotten material. | **Approved** |
| **O3** | No RPO or RTO guarantee or target is established. Elapsed-time measurements are informational only. Any proposed target needs a later measured rehearsal and explicit approval. | **Approved** |
| **O4** | Approved-job and reminder-worker process-kill tests belong in a later, separate specification and are not part of Spec 074. | **Approved** |
| **O5** | An optional independently supplied expected manifest hash may be used. A match proves only equality with the supplied value. States: `freshness_not_evaluated`, `freshness_match`, `freshness_mismatch`. | **Approved** (governance of the retained hash is deferred, 10.2) |
| **O6** | HMAC for this specification, with the limitation that every holder of the verification secret can also create a valid manifest. No separation of duties or public-key verification is claimed. | **Approved** |
| **O7** | The installation UUID is operator-declared and independently pinned as an external expected value, authenticated as part of the manifest and then compared with the supplied expectation. It does not prove the dump's origin. | **Approved** |
| **O8** | Provisional approval of the six limits supported by existing code or stated as provisional engineering limits (section 3.8), with provenance. Not validated operational capacity. | **Approved provisionally** |
| **O9** | No real key-generation command or provisioning workflow in this slice; a synthetic test helper may be used in future engineering tests. | **Approved** |
| Archive expectation | Archive field optional in the format. **`--expect-archive present\|absent` is mandatory on every `generate` and `verify` invocation**, explicitly supplied by the operator, compared with the actual set, never derived from the manifest. | **Approved** |
| Operator notes | No free-text operator note field. | **Approved** |
| Staged restore | A future restore procedure should operate on the exact staged copy that was verified (design principle for a later restore specification only). | **Approved as a principle** |

| Hard-link rejection | A hard-linked recovery-set member is a mandatory failure. | **Approved** |
| Write permissions | Group or other write permission on recovery-set files fails (mandatory); for the key file, group or other read or write fails. | **Approved** |
| Read permissions | Group or other **read** permission on recovery-set files is a mandatory failure, and group or other read permission on the manifest file is also a mandatory failure. No informational note substitutes for these failures or implies confidentiality protection. | **Approved** (14 November 2026, final decision) |
| `expectations` field | The fourth result field `expectations`, distinct from integrity and authenticity. | **Approved** |
| Expected-hash mismatch | A supplied expected manifest hash that does not match always fails, even without `--require-freshness`; that flag controls only whether a hash must be supplied. | **Approved** |
| Installation identity semantics | The key-authenticated installation identity is part of authenticity; comparison with the independently supplied expected UUID belongs to `expectations`. | **Approved** |
| Reason codes and T44 to T54 | The additional reason codes and tests T44 to T54, subject to complete and consistent definitions (sections 7.3.0 and 11.2). | **Approved in principle** |
| 64 GiB dump ceiling | **Not approved as a fixed operational capacity limit.** Synthetic implementation uses small fixtures and injected test limits; the real operational ceiling is deferred to measured resource testing and a separate owner decision. | **Not approved; deferred** |

Note on O8: the six limits approved provisionally are archive entries, archive object size, archive payload, key file size, manifest size and read buffer. Of these, four are existing-code-derived and two (manifest, buffer) are provisional engineering limits, as section 3.8 states. The dump ceiling is **not** among them; 64 GiB appears only as a labelled placeholder.

### 10.2 Deferred decisions (not decided, not assumed)

- **O1b:** the real-world key holder, custody arrangement, storage location, access procedure, backup and loss-recovery procedure. Needed before any real-key or real-set use.
- **O2 retention:** manifest retention, backup and archive retention, expected-hash record retention, and forgetting and deletion reconciliation. A separate governance decision.
- **O5 governance:** who records, retains and updates the expected manifest hash, and how it is kept independent. Needed before freshness is relied on.
- **O7 binding:** database binding or restore-time identity verification, deferred to a later restore specification.
- **O8 dump ceiling:** the real operational dump-size ceiling, deferred to measured resource testing and a separate owner decision. 64 GiB is not approved.
- **O9 tooling:** real key-generation tooling, deferred until key custody and ownership are decided.
- **O4:** the later process-kill specification and its scheduling.
- **Staged restore:** the design of staging and restore itself, deferred to the restore specification.

### 10.3 Open questions requiring owner input

**None remain for freezing.** The earlier question about group or other read permission is resolved: it is a mandatory failure (section 10.1). Resolved questions: `--expect-archive` is mandatory; hard-link, group or other write and group or other read rejection are mandatory; the `expectations` field is approved; the dump ceiling is not approved and is deferred. The deferred decisions of section 10.2 are not questions for freezing; they block real-key and real-set use.

The owner froze this specification on 14 November 2026 (see the freeze record at the top). Implementation remains a further, separate authorization that has **not** been given.

## 11. Acceptance criteria, adversarial tests and evidence boundaries

All tests use synthetic data and synthetic keys. Tests that need no database run in the ordinary backend suite; the drill that uses a real dump runs in the hosted `postgres:17` service container. No browser tests are required because the slice has no UI. **No test is implemented by this specification.**

### 11.1 Acceptance criteria

1. **A1 Valid set.** A synthetic set (a dump file, an archive with marker, lock and several objects) with a manifest generated under a synthetic key verifies with `integrity_valid`, `authenticity_valid`, `expectations_met`, `freshness_not_evaluated`, exit 0.
2. **A2 Separation and state model.** Every output, reason code and document uses the states of section 2.5; a unit test asserts the output key set, every combination row of section 2.5, and that "latest", "current", "fresh" and "up to date" never appear in any output.
3. **A3 Deterministic generation** (section 4.4), including enumeration-order independence.
4. **A4 Closed set**: all violations of section 3.4 are rejected with their closed codes and nothing is read outside the allowlist.
5. **A5 External trust inputs**: every required input is mandatory; none is taken from candidate files; the tool refuses to run with a missing or malformed input before touching any file. (Once every input shape is valid, the overlap pre-check may inspect path metadata solely to detect overlap and aliases, within the bounds of section 2.5; post-freeze clarification of 17 November 2026.)
6. **A6 Freshness never overstates**: section 2.3, the precedence of section 2.5 and the tests below; a match is never reported for an unparseable or unauthenticated manifest.
7. **A7 Atomic generation**: G1 to G9, including the stage distinction of section 9.1 and the unsupported-filesystem behaviour.
8. **A7a Informational notes**: `notes` is bounded, closed, non-leaking and separate from `reasons` (section 7.3.1).
9. **A7b Archive quiescence**: pending objects and change during generation never yield a manifest or a successful verification (section 3.7).
10. **A8 No secrets or foreign paths in any output.**
11. **A9 Point-in-time limitation demonstrated** (section 8), and `verified_references` present only when integrity, authenticity and expectations hold.
12. **A10 No database, network or write to the set**: asserted by running the verifier with sockets disabled (the suite already uses `--disable-socket`) and a read-only set, and by a test that fails if the tool opens a database connection or writes inside `SET`.
13. **A11 Work behaviour unchanged**: the existing Work suppression and authentication tests pass unmodified; no Work module changes.
14. **A12 No migration**: the alembic revision list and head are unchanged by the implementation, and the CI drill still asserts the restored head.
15. **A13 Limits and provenance**: each limit of section 3.8 is enforced with its closed code through an injected test limit and small fixtures (no 64 GiB data), the injection point is unreachable from the command line, environment and configuration, and no test or document presents a provisional limit, the unapproved dump-ceiling placeholder or a synthetic timing as validated capacity.

### 11.2 Positive and negative test matrix

| # | Case | Expected |
|---|---|---|
| T1 | Valid recovery set | A1 outcome |
| T2 | Missing required file (`database.dump`; an archive object listed in the manifest) | `set_member_missing`, `integrity_invalid` |
| T3 | Unexpected extra file; unexpected extra directory | `set_member_unexpected` / `set_directory_unexpected` |
| T4 | Size mismatch (truncated, extended) | `set_member_size_mismatch` |
| T5 | Hash mismatch with unchanged size (one flipped byte) | `set_member_hash_mismatch` |
| T6 | Symlink member; symlinked `SET`; symlinked archive directory; FIFO, socket and device substitutes; hard-linked member | `set_member_symlink` / `set_member_not_regular` / `set_member_hardlinked` |
| T7 | Absolute path, `..` traversal, backslash, NUL, empty segment, over-length segment, case-variant duplicate, Unicode look-alike in a manifest member | `manifest_path_unsafe` / `set_enumeration_ambiguous`, no filesystem access beyond the set |
| T8 | Duplicate JSON key at top level and nested | `manifest_duplicate_key` |
| T9 | Unknown field at every depth | `manifest_unknown_field` |
| T10 | Malformed JSON; valid JSON that is not canonical (whitespace, key order, escapes) | `manifest_malformed` / `manifest_noncanonical` |
| T11 | Unsupported or missing `schema_version`; wrong `purpose` | `manifest_schema_unsupported` |
| T12 | Oversized manifest; oversized key file | `manifest_too_large` / `key_file_unsafe` |
| T13 | Missing key file; unreadable; wrong mode; symlink; group-readable key; hard-linked key | `key_file_unsafe`; `authenticity_invalid` |
| T14 | Incorrect key (valid format, different material) with its own correct fingerprint | `manifest_authentication_failed` / `manifest_key_reference_mismatch` |
| T15 | Correct key with an incorrect expected fingerprint | `key_fingerprint_mismatch` |
| T16 | Wrong namespace: a spec 033 Work key file used as the recovery key | `key_namespace_mismatch` |
| T17 | Key bound to installation B used with a manifest that declares installation A (MAC valid under that key) | `key_installation_mismatch`; `authenticity_invalid`; `integrity_not_evaluated`; `expectations_not_evaluated`; `freshness_not_evaluated` |
| T18 | Key and manifest both bound to installation B, `--expected-installation-id` is A | `authenticity_valid`; `installation_mismatch`; `expectations_not_met`; exit 1 |
| T19 | Schema head mismatch; declared chain with a duplicate or wrong tail; a declared revision the verifier does not know | `schema_head_mismatch` / `schema_chain_inconsistent` / `schema_unknown_to_verifier` |
| T20 | `--require-freshness` with no expected hash | `freshness_requested_without_expected_hash`, exit 2, no file read; with a hash supplied the flag adds no other condition |
| T21 | A correctly authenticated **older** manifest, no expected hash | `integrity_valid`, `authenticity_valid`, `expectations_met`, **`freshness_not_evaluated`**, exit 0 |
| T22 | The same older manifest with an expected hash that belongs to a newer manifest | `freshness_mismatch`; reason `freshness_expected_hash_mismatch`; exit 1 (with or without `--require-freshness`) |
| T23 | A manifest equal to the supplied expected hash | `freshness_match` and `freshness_note: matches_supplied_expected_hash_only`; no output string says latest, current or fresh; exit 0 |
| T24 | Key rotation: manifest under K1 verified with K2 and fingerprint(K2); with K1 and fingerprint(K2); with K1 and fingerprint(K1) | the first two fail (`manifest_key_reference_mismatch` / `key_fingerprint_mismatch`); the third passes |
| T25 | Cross-installation substitution: a complete valid set and manifest for installation B presented for installation A, with B's key and B's fingerprint; with A's key and fingerprint; with B's key and A's fingerprint | `installation_mismatch` (authenticity valid, expectations not met) / `key_installation_mismatch` / `key_fingerprint_mismatch` |
| T26 | Manifest and set re-created together by an attacker without the key | `authenticity_invalid`; `integrity_not_evaluated` |
| T27 | Interrupted generation: SIGKILL at controlled points (before the temporary is complete; after it is flushed, before publication; after publication, before the directory flush) | the final path is absent or holds a complete valid manifest (never a prefix); in the first two points it is absent and a following `generate` succeeds; at the third point a complete final manifest may exist and a following `generate` fails with `output_exists`; a leftover temporary is not mistaken for a manifest, not deleted, and appears as the `stale_temporary_present` note |
| T28 | Existing destination manifest | `output_exists`; existing bytes unchanged |
| T29 | Concurrent generation to one output path (several processes) | exactly one succeeds; the others `output_exists`; the published manifest verifies |
| T30 | Concurrent generation to different outputs | all succeed and are identical when inputs are identical |
| T31 | Filesystem errors (read-only output directory, full filesystem simulated, member removed mid-run) | `io_error` or `set_changed_during_read`; no final manifest |
| T32 | File modified after a successful verification | the first result stands as a point-in-time observation; a second `verify` fails; the test is named as a demonstration of the limitation |
| T33 | Key material in output | the key bytes, hex, base64 and repr are absent from stdout, stderr, written files and logs, including for crashing inputs |
| T34 | Output allowlist | no host path, exception text or traceback appears for any failing case |
| T35 | Bounds: 8194 members; oversize archive object; manifest at the limit and one byte over; dump over the ceiling. **Every limit is exercised with small synthetic fixtures and an injected test limit; no test uses 64 GiB of data** | `set_entry_limit_exceeded` / `set_size_limit_exceeded` / `manifest_too_large` before hashing; constant memory |
| T36 | Manifest and set paths overlap (`MANIFEST` inside `SET`, key inside `SET`) | `paths_overlap`, exit 2 |
| T37 | **Failure before publication** (injected failure at each pre-publication step: set read error, write error to the temporary, flush error, out-of-space, validation failure) | exit 1; `publication: not_published`; no file at the final path; the run's own temporary removed (a remaining one appears as the note on the next run); reason is the specific code, never `publication_durability_uncertain` |
| T38 | **Atomic publication succeeds, then directory `fsync` fails** (fault injection: `EIO`, `EBADF`, persistent `EINTR`) | exit 1; `publication_durability_uncertain`; `publication: published_durability_uncertain`; a complete final manifest exists and is byte-identical to the temporary's content; the run did not delete, rename or modify it; the printed `manifest_hash` equals the hash of the existing file |
| T39 | **The CLI never reports durable success when the directory flush failed or is unconfirmed** | across every T38 variant and one where the flush result cannot be determined: exit never `0`; `published_durable` never appears; `reasons` never empty; no output states or implies the final file is absent |
| T40 | **Retry against an existing final manifest** (after T38 and after a plain pre-existing file) | `output_exists`; exit 1; `publication: not_published`; existing bytes unchanged; no temporary left behind |
| T41 | **Recovery and inspection of a complete but durability-uncertain manifest** (continuing T38) | `verify` gives the same outcomes as for any manifest; after the operator moves the file aside, `generate` to the same path succeeds with `published_durable`; the operator-sync step is outside the tool and no test claims the tool confirms it |
| T42 | **Informational note on a successful run** (a stale temporary is present in the output directory) | exit 0; `reasons: []`; `publication: published_durable`; `notes: ["stale_temporary_present"]`; integrity, authenticity and freshness unaffected |
| T43 | **Notes are bounded and non-leaking** (zero, one and many stale temporaries; adversarial names with control characters, long names, key-like strings; a failure run with stale temporaries) | `notes` contains only vocabulary strings, no duplicates, sorted, at most 4; no name, count or path appears; on failure the same notes may appear beside the failure reason without changing it; `verify` never emits `stale_temporary_present`; a stale temporary inside `SET` yields `set_member_unexpected`, not a note |
| T44 | **Malformed manifest with an expected hash supplied** | `integrity_invalid`; `authenticity_not_evaluated`; `expectations_not_evaluated`; `freshness_not_evaluated`; exit 1 |
| T45 | **Invalid MAC with an expected hash equal to the computed hash** | `authenticity_invalid`; `integrity_not_evaluated`; `freshness_not_evaluated` (never `freshness_match`); exit 1 |
| T46 | **Valid authenticity, no expected hash** | `freshness_not_evaluated`; not a failure; exit 0 |
| T47 | **`--require-freshness` with an authentication failure, and with `freshness_not_evaluated` for any other cause** | exit 1; the cause plus `freshness_required_not_established` |
| T48 | **Archive expectation**: expect `present` against a manifest declaring `absent`; expect `absent` against a manifest declaring `present`; expect `present`, manifest `present`, archive directory removed; expect `absent`, manifest `absent`, archive directory present; `--expect-archive` omitted from `verify` and from `generate` | `archive_expectation_mismatch` / `archive_expectation_mismatch` / `set_member_missing` / `set_directory_unexpected` / `trust_input_missing` (exit 2, no file read); the expectation is never read from the manifest |
| T49 | **Pending archive objects** (`.pending-*` present in `archive/`) in `generate` and in `verify` | `archive_pending_objects_present`; nothing published; the pending object is not omitted, hashed or ignored |
| T50 | **Archive changes during generation** (object added, removed, or modified between the two enumeration passes; a pending object appearing between them) | `archive_changed_during_generation`; nothing published |
| T51 | **Unsupported filesystem** (simulated absence of a no-replace primitive: link and no-replace rename refused; directory `fsync` unsupported) | `filesystem_unsupported` (or `publication_durability_uncertain` for a failed directory flush after publication); `publication: not_published` for the former; no fallback to a replacing rename; no overwrite |
| T52 | **Mode and link invariants (all mandatory failures)**: member writable by group or other; member readable by group or other (each of group-read and other-read); `SET` or `archive/` readable or writable by group or other; manifest file readable by group or other; manifest file writable by group or other; member hard-linked; key file with any group or other bit (read, write); and the passing case: owner-only members, directories and manifest | `set_member_unsafe_mode` / `set_member_unsafe_mode` / `set_member_unsafe_mode` / `manifest_file_unsafe` / `manifest_file_unsafe` / `set_member_hardlinked` / `key_file_unsafe` / success. For every failing row `integrity` or `authenticity` is invalid per the table of section 7.3.0 and the exit status is 1. **No `notes` value is emitted for any permission condition, and no output implies confidentiality protection**; `notes` is `[]` for `verify` in every case |
| T53 | **`verified_references`** | present only when integrity, authenticity and expectations all hold; absent for every failure combination of section 2.5; contains only the four named public fields |
| T54 | **Expectations reported separately**: authentic and intact set, wrong expected schema head | `integrity_valid`, `authenticity_valid`, `expectations_not_met`, exit 1 |

### 11.3 PostgreSQL and real-set drill (hosted CI, `postgres:17` service container)

Extend `scripts/test-db-restore.sh` (no application code change beyond the new tool):

1. Take the existing real `pg_dump --format=custom` output and the existing independently copied archive directory, and assemble a set directory from them.
2. Generate a synthetic recovery key with the test helper, record its fingerprint outside the set, and `generate` a manifest with the installation UUID read by the harness from the source database (the harness plays the operator who declares it).
3. `verify` the set (valid), then verify mutated copies for the negative classes that need a real dump and archive (flipped byte in the dump, removed archive object, extra archive object, truncated dump, a dump from a different synthetic installation, an older manifest against a newer set).
4. Restore the dump with `pg_restore` as today and assert that the restored `alembic_version` equals the manifest's declared head and the restored installation id equals the declared installation id. This is drill **evidence** for the declared fields on this synthetic dump; `verify` itself asserts nothing about the dump contents.
5. Record the tool-reported `elapsed_ms` values in the drill log as informational synthetic timings only.

### 11.4 Restart and recovery evidence

The generator is stateless; its restart evidence is T27 to T29 and T37 to T41 (kill or fault, then recover by a fresh process; no partial final manifest, and no claim of durability when the directory flush failed). There is no daemon to restart. Evidence that a *restored system* works is the existing restore drill, unchanged. Worker process-kill evidence is out of scope (O4).

### 11.5 Migration and downgrade

None. The slice adds no migration, schema change, grant or database object. A12 asserts that the migration head is unchanged by the implementation and that the existing single-head and downgrade tests pass unmodified.

### 11.6 Evidence boundaries

The synthetic CI drill establishes a **test result for the defined hosted CI environment only** (the `postgres:17` service container, synthetic data, a synthetic generated key). It does **not** establish: independent verification (a reviewer other than the implementer re-checking at an exact `main` revision); real key custody, a real holder or storage arrangement; that any set is the latest backup; a clean-host rehearsal; RPO or RTO achievement; real NAS or production recoverability; owner acceptance.

### 11.7 What would still be required, in order

1. A separate, narrowly scoped explicit owner authorization for synthetic-only implementation. (The owner's freeze decision of 14 November 2026 is recorded; it is not an implementation authorization.)
2. Implementation merged with PR evidence (merge commit and PR-head and merge-commit CI recorded separately).
3. Independent verification at an exact `main` revision, with full rather than scope-reduced coverage.
4. Owner decisions on the deferred matters of section 10.2 (key holder and custody, retained-hash governance, retention policy, and a measured and separately approved dump ceiling) and a reviewed procedure using them on a real set.
5. A later restore specification implementing the staged-restore principle, and a clean-host rehearsal on an independent compatible host (a separate gate).
6. Owner acceptance naming environment and scope.

### 11.8 Limits of the synthetic drill and test suite

The future synthetic tests are deliberately weak evidence in these specific ways, and no report may overstate them:

- **A synthetic, database-derived installation ID is not independent proof of the original installation identity.** The drill harness declares the installation id from the same database it then restores, so the match is circular; it shows consistency of the tooling, not provenance.
- **Small synthetic fixtures and injected test limits do not validate behaviour at any real dump size, including the 64 GiB placeholder.** Time and resource behaviour for large dumps is untested; the real operational ceiling is deferred to measured resource testing and a separate owner decision. A passing limit test shows only that the logic reacts to the injected limit.
- **Synthetic tests do not establish real NAS, USB or network filesystem behaviour.** They exercise whatever local filesystem the CI runner provides, plus injected faults.
- They do not establish clean-host recovery, do not close the verification-to-restore gap (the drill verifies and restores the same bytes in one controlled script), and do not establish RPO or RTO.
- Elapsed times are informational only and prove nothing about recovery objectives.
- Passing the suite shows that the implementation meets this specification on synthetic data in that environment; it does not show that any real set is intact, authentic, current, complete or recoverable.

## 12. Dependencies and blockers

- **Dependencies:** none new. Python standard library (`hmac`, `hashlib`, `secrets`, `json`, `os`, `stat`), the already-present Pydantic models pattern, and existing modules read-only. No new package, service, schema, grant or compose change.
- **Open questions:** none remain (section 10.3). The group or other read-permission question is resolved as a mandatory failure (section 10.1).
- **Freezing:** done. The owner decided to freeze this specification on 14 November 2026 (freeze record at the top). No further answer was outstanding.
- **Needed before any implementation:** a separate explicit owner authorization (not given). Freezing does not itself authorize implementation.
- **Needed before any real-key or real-set use:** the deferred decisions of section 10.2 (O1b, retained-hash governance, retention policy, a measured and approved dump ceiling, and key tooling).
- **Blockers for the wider recovery programme (not this slice):** an independent clean compatible host, a reviewed key-recovery policy, the restore specification, DOC-X02 reconciliation design for non-Work records.
