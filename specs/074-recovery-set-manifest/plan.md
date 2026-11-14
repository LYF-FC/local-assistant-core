# Spec 074 plan, checklist and analysis

**Draft for owner review. Nothing here is implemented, frozen, verified, merged or accepted, and this document does not authorize implementation.** It accompanies [spec.md](spec.md) and follows the "Plan / analyze" pattern of spec 071.

## 1. Plan (proposal, conditional on owner decisions O1 to O9)

### 1.1 Shape

A standalone offline command, `python -m app.recovery_set generate|verify` (module name proposed), in a new `backend/app/recovery_set/` package, with no FastAPI route, no worker, no router registration, no settings entry, no model, no migration and no compose or Dockerfile change. Proposed split:

| Unit | Responsibility |
|---|---|
| `format.py` | Closed Pydantic models (`extra=forbid`), canonical JSON, duplicate-key hook, manifest hash, limits |
| `key.py` | Key file model, namespace and installation binding, fingerprint and MAC domains, masked secret type |
| `fsset.py` | Descriptor-relative closed-set enumeration and streaming hashing (spec section 3.4) |
| `publish.py` | Atomic, exclusive, durable manifest publication (spec section 9.1) |
| `verify.py` / `generate.py` | Evaluation order (spec section 7.2) and result model |
| `cli.py` | Argument parsing, closed output, exit statuses, exception boundary |

Reuse of `work_suppression_file.py` primitives is allowed only by importing without modifying them; if their signatures do not fit, the unit re-implements the same behaviour rather than altering Work code (acceptance A11).

### 1.2 Proposed staging (each stage independently testable)

1. Format, canonical JSON, key model, domains (unit tests T8 to T16, T24).
2. Closed-set enumeration and hashing (T2 to T7, T35, T36).
3. Verification flow and output model (T1, T17 to T23, T25, T26, T33, T34).
4. Atomic generation (T27 to T31).
5. PostgreSQL drill in `scripts/test-db-restore.sh` and a CI step (section 11.3 of the spec), plus documentation (`docs/` recovery-set page, operations overview cross-reference, no status changes).

### 1.3 Files that an implementation would touch (informational)

New: `backend/app/recovery_set/*`, `backend/tests/test_recovery_set_*.py`, a synthetic key helper under `backend/tests/`, one documentation page. Modified: `scripts/test-db-restore.sh` and its CI invocation only. **Not modified:** any migration, `app/main.py`, routes, settings, Work modules, frontend, compose files, runtime images.

### 1.4 Security and quality gates for an implementation

`ruff`, `ruff format --check`, `bandit` (the tool uses `hmac`, `hashlib`, `os.open`; no subprocess, no shell, no network), full non-integration suite, integration suite in CI shape, `scripts/check_repository.py`, `build_feature_overview.py --check`. Mutation checks recommended for: dropping the expected-fingerprint check, dropping the installation binding, dropping the domain prefix, dropping the closed-set "unexpected" check, dropping the post-hash `fstat`, using `os.rename` instead of a no-replace link, and removing directory `fsync`.

## 2. Checklist (requirements quality)

| # | Check | Result |
|---|---|---|
| C1 | Integrity, authenticity and freshness are separate in output, codes, docs and tests | Specified (spec 2, 7.3, A2) |
| C2 | No output or doc claims latest/current/fresh without an independent expected value | Specified; string-absence test in A2 and T23 |
| C3 | Every trust input has a stated external provenance and none is read from the manifest | Specified (spec 5) |
| C4 | Key custody holder and storage are not invented | Satisfied: responsibilities only (spec 6.5); O1 open |
| C5 | No real key generation, provisioning or use | Satisfied; synthetic test helper only; O9 |
| C6 | Key material never in output, manifests, logs, errors, test artifacts | Specified, tested (T33, T34) |
| C7 | Domain and namespace separation from Work authentication | Specified (spec 4.2, 6.2); T16 |
| C8 | Rotation, replacement, loss, compromise addressed at spec level | Specified (spec 6.6) |
| C9 | HMAC limits stated; asymmetric not assumed | Specified; O6 |
| C10 | Canonical JSON, duplicate keys, unknown fields, versioning | Specified; T8 to T11 |
| C11 | Path, symlink, special-file, traversal, closed-set rules | Specified; T3, T6, T7 |
| C12 | Bounded resource use; safe errors | Specified (3.4, 7.3, 9.4); T35 |
| C13 | Verification-to-restore gap stated with future mitigations, no restore design | Specified (spec 8); T32 |
| C14 | Atomic generation guarantees and failure semantics are observable, not one implementation | Specified (spec 9.1); T27 to T31 |
| C15 | Scope boundaries and non-goals explicit | Specified (spec 9.2) |
| C16 | All required adversarial cases appear in tests | Complete: see mapping in section 3.1 |
| C17 | Evidence boundaries stated; no clean-host, RPO/RTO, real-NAS or acceptance claim | Specified (spec 11.6, 11.7) |
| C18 | No requirement, gate or counter change | Satisfied; spec header and 3.1 |
| C19 | Data-flow statement (constitution I) present | Spec 9.3 |
| C20 | Numeric thresholds defined or marked unconfirmed (MVP_ACCEPTANCE) | Ceilings proposed; unconfirmed until O8 |
| C21 | Migration impact stated | None (spec 11.5, A12) |
| C22 | Premise corrections disclosed | Spec 060 manifest is a test fixture, not a product artifact (spec 3.2) |

## 3. Analysis

### 3.1 Required test coverage mapping

| Required case | Tests |
|---|---|
| valid set | T1 |
| missing required file | T2 |
| extra file or directory | T3 |
| size mismatch / hash mismatch | T4 / T5 |
| symlink and unsafe type | T6 |
| absolute path and traversal | T7 |
| duplicate JSON keys / unknown fields / malformed or noncanonical JSON | T8 / T9 / T10 (T11 for versions) |
| missing or incorrect key | T13 / T14 |
| incorrect expected fingerprint | T15 |
| wrong namespace | T16 |
| wrong installation UUID | T18 (T17, T25) |
| schema-head mismatch | T19 |
| missing expected hash when freshness requested | T20 |
| authenticated older manifest, no expected hash: freshness unestablished | T21 |
| authenticated older manifest against a different expected hash: freshness fails | T22 |
| manifest matching expected hash, comparison-only wording | T23 |
| key rotation, wrong namespace, cross-installation substitution | T24, T16, T25 |
| interrupted generation / existing destination / concurrent generation | T27 / T28 / T29 (T30) |
| modification after verification (point-in-time) | T32 |
| no secrets, key material, content or foreign paths in output | T33, T34 |

### 3.2 Consistency with governance documents

- **Constitution (data flow, restore testing):** offline, no provider, no network (spec 9.3). Restore testing stays the existing drill, extended, never replaced.
- **Decision precedence:** no new owner decision is assumed; each is listed as a proposal (spec 10). DECISIONS.md is untouched.
- **MVP_ACCEPTANCE:** MVP-05 contribution is partial and says so; numeric thresholds are proposed and unconfirmed (C20); no RPO/RTO claim.
- **Specs 033/034:** same primitives and expected-value discipline; the new key is separate, so a leak of one does not authenticate the other.
- **Spec 038:** `recovery_complete` remains false everywhere; this slice adds the same constant to its own output.
- **Spec 050:** archive names and limits reused as the allowlist.
- **AGENTS.md:** synthetic data only; no generated-file edits; status model respected; no acceptance claimed.

### 3.3 Findings and risks

1. **Declared fields are not bound to the dump.** Installation identity and schema head are operator-declared (O7). A key holder can declare anything. Mitigation here is the independent expected values and the drill; real binding is a restore-slice matter.
2. **Premise correction.** No Spec 060 installation manifest exists as a product artifact; the assignment's list was adapted accordingly (spec 3.2).
3. **Missing key-recovery policy.** The Work documents refer to a reviewed encrypted/off-site key policy that is not in the repository. Real use of this slice is blocked on O1 independent of engineering.
4. **Forgotten-object disclosure.** Old manifests keep naming purged documents (spec 9.4, O2). This is a forgetting-governance concern; it is recorded, not solved.
5. **HMAC forging power** (O6) and **TOCTOU** (spec 8) are accepted limitations, stated rather than hidden.
6. **Hard-coded head in the existing drill** (`0038_work_status_audit_category`) means the drill needs updating on every migration; the manifest's declared head should replace that constant when the drill is extended.
7. **Large dumps.** Streaming hashing is constant memory, but run time scales with size; the elapsed time is informational only (O3).
8. **Filesystem durability assumptions** (G5) depend on the storage honouring `fsync`; network or removable media may not. Stated in documentation requirements, not claimed as solved.

### 3.4 Open items that block implementation

O8 (numeric ceilings) before any implementation; O1, O5 and O6 before anything that touches real keys or real sets; O2 retention before real manifests are kept. No other blocker is known.

## 4. Statement of non-action

This draft adds only the three files under `specs/074-recovery-set-manifest/`. It contains no code, test, migration, configuration, key, credential or generated file, and does not change any status, count or gate.
