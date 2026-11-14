# Spec 074 tasks (outline only)

**Draft. No task is started or authorized.** Implementation requires a separate explicit owner authorization after the owner answers the decisions in [spec.md](spec.md) section 10 (at minimum O8; O1, O5, O6 before any real-key use). All boxes stay unchecked until that authorization exists.

## Stage 0: preconditions

- [ ] T000 Owner answers O1 to O9 (or confirms the recommendations) and authorizes implementation in writing.
- [ ] T001 Re-confirm 074 is still the next free spec identifier and re-read `main` at the implementation baseline.

## Stage 1: format and key model

- [ ] T010 Closed manifest models, canonical JSON, duplicate-key and unknown-field rejection, size limits.
- [ ] T011 Manifest hash and MAC with the three new domains (spec 4.2).
- [ ] T012 Key file model, namespace and installation binding, fingerprint, masked secret type.
- [ ] T013 Tests T8 to T16, T24.

## Stage 2: closed-set enumeration

- [ ] T020 Descriptor-relative enumeration, allowlist, mode, link and type checks, deterministic order.
- [ ] T021 Streaming hashing with double `fstat` and bounds.
- [ ] T022 Tests T2 to T7, T35, T36.

## Stage 3: verification

- [ ] T030 Trust-input parsing and the evaluation order of spec 7.2.
- [ ] T031 Closed output object, reason codes, exit statuses, exception boundary.
- [ ] T032 Tests T1, T17 to T23, T25, T26, T33, T34 (including output-string absence checks).

## Stage 4: generation

- [ ] T040 Exclusive temporary file, no-replace atomic publication, file and directory `fsync`, cleanup.
- [ ] T041 Tests T27 to T31 using real subprocesses and SIGKILL at controlled points.
- [ ] T042 Test T32 (point-in-time limitation demonstration).

## Stage 5: drill and documentation

- [ ] T050 Extend `scripts/test-db-restore.sh` with the real-dump drill of spec 11.3 using a synthetic key.
- [ ] T051 Documentation page (integrity, authenticity, freshness; trust inputs; limits; custody responsibilities) and cross-references, with no status change.
- [ ] T052 Quality gates, mutation checks of plan 1.4, hosted CI on the PR head and, separately, on the merge commit.

## Not tasks of this spec

Restoration, key generation tooling (O9), encryption, backup scheduling or freshness services, DOC-X02, worker liveness, RPO/RTO acceptance, clean-host rehearsal.
