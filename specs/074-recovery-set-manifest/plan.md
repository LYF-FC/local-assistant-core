# Spec 074 plan, checklist and analysis

**Draft, revised after the owner decisions of 14 November 2026. Not frozen and not approved for implementation. Nothing here is implemented, verified, merged or accepted, and this document does not authorize implementation.** It accompanies [spec.md](spec.md) and follows the "Plan / analyze" pattern of spec 071. Freezing the specification and authorizing a narrowly scoped synthetic-only implementation are each a separate explicit owner decision.

## 1. Plan (proposal; conditional on a future freeze and implementation authorization)

### 1.1 Shape

A standalone offline command, `python -m app.recovery_set generate|verify` (module name proposed), in a new `backend/app/recovery_set/` package, with no FastAPI route, worker, router registration, settings entry, model, migration, dependency or compose/Dockerfile change. Proposed split:

| Unit | Responsibility |
|---|---|
| `format.py` | Closed Pydantic models (`extra=forbid`), canonical JSON, duplicate-key hook, manifest hash, limits with their provenance classes (spec 3.8) |
| `key.py` | Key file model, namespace and installation binding, keyed fingerprint and MAC domains, masked secret type |
| `fsset.py` | Descriptor-relative closed-set enumeration, pending-object and two-pass change detection, streaming hashing (spec 3.4, 3.7) |
| `publish.py` | No-replace atomic, exclusive, durable manifest publication and capability detection (spec 9.1) |
| `verify.py` / `generate.py` | Stage order and the four-field result model (spec 2.5, 7.2) |
| `cli.py` | Argument parsing, closed output, exit statuses, exception boundary |

Reuse of `work_suppression_file.py` primitives is allowed only by importing without modifying them; where signatures do not fit, the unit re-implements the same behaviour rather than altering Work code (acceptance A11).

### 1.2 Proposed staging (each stage independently testable; none authorized)

1. Format, canonical JSON, key model, keyed fingerprint, domains (tests T8 to T16, T24).
2. Closed-set enumeration, invariants, pending-object handling and limits via injected test limits (T2 to T7, T35, T36, T49, T50, T52; limits exercised through injected test limits and small fixtures only).
3. Verification flow, four-field state model, freshness precedence, archive expectation and `verified_references` (T1, T17 to T23, T25, T26, T33, T34, T44 to T48, T53, T54).
4. Atomic generation and publication stages, including the unsupported-filesystem behaviour and notes (T27 to T31, T37 to T43, T51).
5. PostgreSQL drill in `scripts/test-db-restore.sh` and a CI step (spec 11.3), plus documentation (a `docs/` recovery-set page, an operations-overview cross-reference, no status change).

### 1.3 Files an implementation would touch (informational)

New: `backend/app/recovery_set/*`, `backend/tests/test_recovery_set_*.py`, a synthetic key helper under `backend/tests/`, one documentation page. Modified: `scripts/test-db-restore.sh` and its CI invocation only. **Not modified:** any migration, `app/main.py`, routes, settings, Work modules, frontend, compose files, runtime images, dependencies.

### 1.4 Quality gates for an implementation

`ruff`, `ruff format --check`, `bandit`, full non-integration suite, integration suite in CI shape, `scripts/check_repository.py`, `build_feature_overview.py --check`. Mutation checks recommended for: dropping the expected-fingerprint check; dropping the installation binding; dropping the domain prefix; dropping the closed-set "unexpected" check; dropping the post-hash `fstat`; using a replacing `rename` for publication; removing directory `fsync`; swallowing a directory-`fsync` error; emitting a note outside the vocabulary; reporting `freshness_match` for an unauthenticated manifest; accepting a pending archive object; deriving `--expect-archive` from the manifest.

## 2. Phases are distinct

| Phase | State | What it needs |
|---|---|---|
| Specification (this draft) | Draft, revised after owner decisions | An owner review and a separate owner decision to freeze (no open question remains) |
| Synthetic-only implementation | **Not authorized** | A frozen specification and a separate, narrowly scoped owner authorization |
| Real-key or real-set use | Not possible under this specification | The deferred decisions of spec 10.2 |
| Restore and staging | Out of scope | A later restore specification |

## 3. Checklist (requirements quality)

| # | Check | Result |
|---|---|---|
| C1 | Integrity, authenticity, freshness (and expectations) are separate in output, codes, docs and tests | Specified (spec 2.5, 7.3, A2) |
| C2 | Complete state model with precedence; malformed manifest or bad HMAC never gets a success result; freshness never matches for an unparsed or unauthenticated manifest | Specified (spec 2.5); T44 to T47, T54 |
| C3 | Freshness states are exactly `freshness_not_evaluated`, `freshness_match`, `freshness_mismatch`; no "latest/current/fresh" wording | Specified (spec 2.3, A2) |
| C4 | Every trust input has a stated external provenance and none is read from the manifest, including `--expect-archive` | Specified (spec 5) |
| C5 | Key custody holder and storage are not invented; no reviewed key policy is implied | Satisfied: O1a approved, O1b deferred (spec 6.1, 6.6, 10.2) |
| C6 | No real key generation, provisioning or use; synthetic helper only; no key tooling (O9) | Satisfied |
| C7 | Key material never in output, manifests, logs, errors, test artifacts | Specified, tested (T33, T34) |
| C8 | Domain and namespace separation from Work authentication; keyed fingerprint described as a keyed tag | Specified (spec 4.2, 6.2); T16 |
| C9 | Rotation, replacement, loss, compromise at spec level | Specified (spec 6.7) |
| C10 | HMAC limitation prominent: every verifier-secret holder can forge; no separation of duties claimed (O6) | Specified (spec 6.4) |
| C11 | Generation host is a trust boundary; what the HMAC attests | Specified (spec 6.5) |
| C12 | Canonical JSON, duplicate keys, unknown fields, versioning; no free-text field | Specified (spec 4.1); T8 to T11 |
| C13 | Security invariants separated from filesystem assumptions, informational checks and compatibility; integrity, confidentiality, assumptions and compatibility kept apart; hard-link, group/other write and group/other **read** rejection mandatory for set members, directories and the manifest; key file with any group/other bit fails; no permission note exists, and no note implies confidentiality or substitutes for a failure; no universal portability | Specified (spec 3.4 rule 5, 3.6, 3.6.1, 7.3.1); T52 |
| C14 | Archive quiescence, pending objects, change during generation | Specified (spec 3.7); T49, T50 |
| C15 | Numeric limits with provenance classes; the 64 GiB dump ceiling is an unapproved placeholder (real ceiling deferred to measured testing and a separate decision); test-only limit injection with small fixtures; no 64 GiB data; no capacity claim | Specified (spec 3.8); T35, A13 |
| C16 | Verification-to-restore gap explicit; staged-restore principle recorded for the later specification only; `verified_references` exposed | Specified (spec 8); T32, T53 |
| C17 | Publication stages, no-replace primitive, unsupported-filesystem behaviour, durability, safe retry | Specified (spec 9.1); T27 to T31, T37 to T41, T51 |
| C18 | Informational notes bounded, closed, separate from reasons | Specified (spec 7.3.1); T42, T43 |
| C19 | Scope and assurance statement prominent; exclusions listed; name retained | Specified (spec 0) |
| C20 | Metadata disclosure and the four retention matters distinguished; no durations or policy finalized | Specified (spec 9.4, 10.2) |
| C21 | Out of scope: process-kill tests (O4), restoration, staging, key tooling | Specified (spec 9.2) |
| C22 | Evidence boundaries and synthetic-drill limits stated; no clean-host, RPO/RTO, real-NAS or acceptance claim | Specified (spec 11.6, 11.8) |
| C23 | No requirement, gate, count, priority or acceptance change | Satisfied; spec header and 3.1 |
| C24 | Data-flow statement (constitution I) present | Spec 9.3 |
| C25 | Migration impact stated | None (spec 11.5, A12) |
| C26 | Premise correction disclosed | Spec 060 manifest is a test fixture, not a product artifact (spec 3.2) |
| C27 | Deferred decisions kept deferred and open questions explicit | Spec 10.2, 10.3 (none open) |
| C28 | Every reason code has one meaning, one state effect and one exit status; every approved reason code and T44 to T54 is completely defined | Spec 7.3.0, 11.2 |
| C29 | `--expect-archive` mandatory on every `generate` and `verify`; supplied expected-hash mismatch always fails; `--require-freshness` only requires a hash; key-authenticated installation identity in authenticity, expected-UUID comparison in expectations | Spec 2.2, 2.4, 2.5, 5.1, 5.2; T17, T18, T20, T22, T25, T47, T48 |

## 4. Analysis

### 4.1 Required test coverage mapping

| Required case | Tests |
|---|---|
| valid set | T1 |
| missing required file / extra file or directory | T2 / T3 |
| size mismatch / hash mismatch | T4 / T5 |
| symlink and unsafe type / mode and link invariants | T6 / T52 |
| absolute path and traversal | T7 |
| duplicate JSON keys / unknown fields / malformed or noncanonical JSON | T8 / T9 / T10 (T11 for versions) |
| missing or incorrect key / incorrect expected fingerprint | T13, T14 / T15 |
| wrong namespace / wrong installation UUID / schema-head mismatch | T16 / T18 (T17, T25) / T19, T54 |
| archive expectation (present vs absent, never from the manifest) | T48 |
| missing expected hash when freshness requested | T20 |
| authenticated older manifest, no hash: `freshness_not_evaluated` | T21 |
| authenticated older manifest, different hash: `freshness_mismatch` | T22 |
| manifest equal to the expected hash: `freshness_match`, comparison-only wording | T23 |
| freshness precedence (malformed manifest, invalid MAC, required but not established) | T44, T45, T46, T47 |
| key rotation, wrong namespace, cross-installation substitution | T24, T16, T25 |
| interrupted generation / existing destination / concurrent generation | T27 / T28 / T29 (T30) |
| failure before publication | T37 |
| publication success then directory `fsync` failure | T38 |
| CLI never reports durable success in that case | T39 |
| retry against an existing final manifest | T40 (T28) |
| recovery and inspection of a complete, durability-uncertain manifest | T41 |
| unsupported filesystem, no replacing fallback | T51 |
| pending archive objects / archive change during generation | T49 / T50 |
| informational notes: success, bounds, non-leaking; no permission note | T42, T43, T52 |
| group/other read or write on members, directories, manifest; key file bits | T52 |
| `verified_references` only when integrity, authenticity and expectations hold | T53 |
| limits enforced from `fstat` before hashing | T35 |
| modification after verification (point-in-time) | T32 |
| no secrets, key material, content or foreign paths in output | T33, T34 |

### 4.2 Consistency with governance documents

- **Constitution (data flow, restore testing):** offline, no provider, no network (spec 9.3). Restore testing stays the existing drill, extended, never replaced.
- **Decision precedence:** the owner decisions O1a, O2 (content), O3 to O9, the archive expectation, the operator-notes decision and the staged-restore principle are recorded as approved direction; every deferred matter stays deferred (spec 10). DECISIONS.md is untouched.
- **MVP_ACCEPTANCE:** MVP-05 contribution is partial and the exclusions are stated (spec 0); numeric thresholds are provenance-classified and the provisional ones are not passing evidence; no RPO/RTO claim.
- **Specs 033/034:** same primitives and expected-value discipline; the new key is separate, so a leak of one does not authenticate the other.
- **Spec 038:** `recovery_complete` remains false everywhere; this slice adds the same constant to its own output.
- **Spec 050:** archive names, limits and the pending-object pattern reused as the allowlist and the quiescence rule.
- **AGENTS.md:** synthetic data only; no generated-file edits; status model respected; no acceptance claimed.

### 4.3 Findings and residual risks

1. **Declared fields are not bound to the dump** (O7, approved as declared plus pinned). A key holder can declare anything; binding is deferred to the restore specification.
2. **Generation-host trust boundary** (spec 6.5): the HMAC proves only that a key holder authenticated the manifest bytes. It does not make the dump genuine, complete, current or recoverable.
3. **Missing key-recovery policy.** The Work documents refer to a reviewed encrypted/off-site key policy that is not in the repository. Real use is blocked on O1b independent of engineering.
4. **Forgotten-object disclosure.** Old manifests keep naming purged documents (spec 9.4). A governance concern, recorded and deferred.
5. **HMAC forging power** (O6) and **the verification-to-restore gap** (spec 8) are accepted, stated limitations, not hidden ones.
6. **Hard-coded head in the existing drill** (`0038_work_status_audit_category`) means the drill needs updating on every migration; the manifest's declared head should replace that constant when the drill is extended.
7. **Large dumps.** Streaming hashing is constant memory, but run time scales with size. The 64 GiB figure is an **unapproved placeholder**, not an approved operational ceiling and not a measured capacity. The real operational ceiling requires measured resource testing and a separate owner decision; until then no real set may be treated as supported by it, and synthetic tests use small fixtures with injected limits.
8. **Filesystem assumptions.** Publication and verification are specified for a local POSIX filesystem on Linux only; other media fail closed or must be copied to a supported filesystem (spec 3.6 Class 4). Hard-linked snapshot trees must be copied, not linked.
9. **Archive quiescence is an operator precondition.** The tool detects observable change and pending objects but cannot prove quiescence or DB-archive consistency.
10. **Revision note (14 November 2026).** This draft was revised to incorporate the owner decisions and corrections: the complete state model and freshness precedence, the keyed-fingerprint wording, the generation-host trust boundary, the invariant/assumption/informational/compatibility separation, the no-replace publication primitive and unsupported-filesystem behaviour, archive quiescence, the scope and assurance statement, the synthetic-drill limits and the limit-provenance classes. Earlier revisions corrected G1, G5 and G7 by publication stage and defined the `notes` field. No deferred decision was resolved.
11. **Second revision (14 November 2026, final owner decisions).** `--expect-archive` is mandatory on every `generate` and `verify`; hard-link and group/other write rejection are mandatory; the `expectations` field is approved; a supplied expected-hash mismatch always fails and `--require-freshness` only requires a hash; the key-authenticated installation identity is part of authenticity and the expected-UUID comparison belongs to `expectations`; reason codes now have complete definitions (spec 7.3.0). Permissions were reworked into integrity, confidentiality, assumptions and compatibility (spec 3.6.1) and the group/other **read** policy was left explicitly unresolved at that revision with no confidentiality claim (resolved in the third revision below). The 64 GiB dump ceiling is an unapproved placeholder, and the synthetic implementation uses small fixtures with test-only injected limits.
12. **Third revision (14 November 2026, final permission decision).** Group or other **read** permission on recovery-set files, `SET`, `archive/` and the manifest file is a mandatory failure, in addition to the already mandatory group/other write and hard-link failures; the key file rule is unchanged. The informational `set_mode_group_or_other_readable` note is removed, so the only note is `stale_temporary_present`. The unresolved read-permission question is removed from the open items and the freeze blockers. Reason-code definitions, state and exit behaviour, T43 and T52, the plan and the tasks were updated to match.

### 4.4 Open items

No question remains open for freezing (spec 10.3). The owner has resolved `--expect-archive` (mandatory), hard-link, group/other write and group/other read rejection (mandatory, for recovery-set files and the manifest), the `expectations` field (approved) and the dump ceiling (not approved, deferred). The deferred decisions of spec 10.2 do not block a synthetic-only implementation, which uses small fixtures and injected test limits; they block real-key and real-set use. Freezing and implementation each remain a separate explicit owner decision, neither given.

## 5. Statement of non-action

This draft adds only the three files under `specs/074-recovery-set-manifest/`. It contains no code, test, migration, configuration, key, credential or generated file, and does not change any status, count or gate.
