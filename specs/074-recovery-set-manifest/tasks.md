# Spec 074 tasks (outline only)

**Specification FROZEN (owner decision of 14 November 2026; frozen revision is the content of commit `f903237a69e6e2eeeef8b057abef3fc618a27630`). Phase A is closed. No implementation task is started or authorized, and every Phase B and C box stays unchecked.** The phases are distinct and each needs its own explicit owner decision; the freeze is not an implementation authorization.

## Phase A: specification (this document set)

- [x] A1 Owner review of the revised specification. Done 14 November 2026: the owner reviewed and approved it. (No open question remained: [spec.md](spec.md) section 10.3.)
- [x] A2 Owner decision to freeze the specification. Done 14 November 2026: frozen; frozen revision is the content of commit `f903237a69e6e2eeeef8b057abef3fc618a27630` (see the freeze record in [spec.md](spec.md)). This is not an implementation authorization.

## Phase B: synthetic-only implementation (not authorized; requires the frozen specification (A2, done) and a separate, narrowly scoped owner authorization)

### B0 preconditions

- [ ] B000 Written owner authorization for synthetic-only implementation.
- [ ] B001 Re-confirm 074 is still the next free spec identifier and re-read `main` at the implementation baseline.

### B1 format and key model

- [ ] B010 Closed manifest models, canonical JSON, duplicate-key and unknown-field rejection, size limits, no free-text field.
- [ ] B011 Manifest hash, MAC and keyed fingerprint with the three new domains (spec 4.2).
- [ ] B012 Key file model, namespace and installation binding, masked secret type.
- [ ] B013 Tests T8 to T16, T24.

### B2 closed-set enumeration

- [ ] B020 Descriptor-relative enumeration, allowlist, invariants (including mandatory group/other read and write failures), and the single informational note `stale_temporary_present`, deterministic order (spec 3.4, 3.6).
- [ ] B021 Pending-object refusal and two-pass change detection (spec 3.7).
- [ ] B022 Streaming hashing with double `fstat`, limits with provenance classes, and a test-only limit injection point unreachable from the command line, environment and configuration (spec 3.8).
- [ ] B023 Tests T2 to T7, T35 (injected limits, small fixtures, no 64 GiB data), T36, T49, T50, T52.

### B3 verification

- [ ] B030 Trust-input parsing (including `--expect-archive`) and the stage order of spec 2.5, 7.2.
- [ ] B031 Four-field result model, freshness precedence, `verified_references`, closed output object, reason codes, exit statuses, exception boundary.
- [ ] B032 Tests T1, T17 to T23, T25, T26, T33, T34, T44 to T48, T53, T54.

### B4 generation

- [ ] B040 Exclusive temporary file, no-replace atomic publication, capability detection and `filesystem_unsupported`, file and directory `fsync`, cleanup (spec 9.1).
- [ ] B041 Tests T27 to T31 and T37 to T41 using real subprocesses, SIGKILL at controlled points and fault injection at the pre-publication steps and the directory flush; T51.
- [ ] B042 Informational `notes` field and tests T42, T43 (spec 7.3.1).
- [ ] B043 Test T32 (point-in-time limitation demonstration).

### B5 drill and documentation

- [ ] B050 Extend `scripts/test-db-restore.sh` with the real-dump drill of spec 11.3 using a synthetic key; state the limits of spec 11.8 in the drill log.
- [ ] B051 Documentation page (integrity, authenticity, freshness and expectations; trust inputs; generation-host trust boundary; HMAC limitation; filesystem assumptions; custody responsibilities) and cross-references, with no status change.
- [ ] B052 Quality gates, mutation checks of plan 1.4, hosted CI on the PR head and, separately, on the merge commit.

## Phase C: before any real-key or real-set use (deferred, not part of this slice)

- [ ] C1 Key holder, custody, storage, access, backup and loss-recovery procedure (O1b).
- [ ] C2 Governance of the independently retained expected manifest hash (O5).
- [ ] C3 Retention policy for manifests, backups and archives, expected-hash records, and forgetting reconciliation (O2).
- [ ] C4 Measured resource testing and a separate owner decision on the real operational dump ceiling (O8); 64 GiB is not approved.
- [ ] C5 Real key-generation tooling and provisioning workflow, after custody is decided (O9).

## Not tasks of this spec

Restoration and staging (a later restore specification, including database binding of the installation identity and restore from the exact verified staged copy); approved-job and reminder-worker process-kill tests (a later, separate specification, O4); encryption; backup scheduling or freshness services; DOC-X02; worker liveness; RPO/RTO acceptance; clean-host rehearsal.
