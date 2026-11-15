**Specification FROZEN (owner decision of 14 November 2026; frozen revision is the content of commit `f903237a69e6e2eeeef8b057abef3fc618a27630`). Phase A is closed and the specification remains frozen. The owner separately authorized Phase B synthetic-only implementation, which was implemented and merged in PR #40 (merge commit `47b949e61c96a2e3c2fd883e1784a2856946146c`). B050 and B052 are complete on the recorded synthetic-only validation evidence. The owner formally accepted synthetic-only Phase B on 15 November 2026. The owner acknowledged and accepted the two documented implementation interpretations (only the first violation is reported under the closed output schema; a stale temporary link after confirmed durability leaves the resulting set unverifiable until it is removed). On 15 November 2026 the owner authorized Phase C design and preparatory work only; the owner then also authorized implementation of the non-operational portions of Phase C (see [DECISIONS.md](../../DECISIONS.md)). The Phase C tasks stay unchecked, and key-generation or key-management tooling, any real-key or real-set use and every other operational activity are not authorized.** Authorization, implementation, verification, merge and acceptance are distinct. The phases are distinct and each needs its own explicit owner decision; the freeze is not an implementation authorization.



## Phase A: specification (this document set)

- [x] A1 Owner review of the revised specification. Done 14 November 2026: the owner reviewed and approved it. (No open question remained: [spec.md](spec.md) section 10.3.)
- [x] A2 Owner decision to freeze the specification. Done 14 November 2026: frozen; frozen revision is the content of commit `f903237a69e6e2eeeef8b057abef3fc618a27630` (see the freeze record in [spec.md](spec.md)). This is not an implementation authorization.

## Phase B: synthetic-only implementation (separately authorized by the owner, limited to the approved Phase B scope; this does not authorize Phase C or any real-key or real-set operation)

### B0 preconditions

- [x] B000 Written owner authorization for synthetic-only implementation. Authorized by written owner instruction of 14 November 2026 (Phase B, synthetic-only, B010 to B052).
- [x] B001 Re-confirm 074 is still the next free spec identifier and re-read `main` at the implementation baseline. Intent satisfied at main `355fd6fce2cb6d4874163c6fc377852c9550d104` (merge of PR #39): 074 is the unique assigned identifier, 075 is the next free one, frozen revision and freeze commit are ancestors, no intervening changes or new dependencies.

### B1 format and key model

- [x] B010 Closed manifest models, canonical JSON, duplicate-key and unknown-field rejection, size limits, no free-text field.
- [x] B011 Manifest hash, MAC and keyed fingerprint with the three new domains (spec 4.2).
- [x] B012 Key file model, namespace and installation binding, masked secret type.
- [x] B013 Tests T8 to T16, T24.

### B2 closed-set enumeration

- [x] B020 Descriptor-relative enumeration, allowlist, invariants (including mandatory group/other read and write failures), and the single informational note `stale_temporary_present`, deterministic order (spec 3.4, 3.6).
- [x] B021 Pending-object refusal and two-pass change detection (spec 3.7).
- [x] B022 Streaming hashing with double `fstat`, limits with provenance classes, and a test-only limit injection point unreachable from the command line, environment and configuration (spec 3.8).
- [x] B023 Tests T2 to T7, T35 (injected limits, small fixtures, no 64 GiB data), T36, T49, T50, T52.

### B3 verification

- [x] B030 Trust-input parsing (including `--expect-archive`) and the stage order of spec 2.5, 7.2.
- [x] B031 Four-field result model, freshness precedence, `verified_references`, closed output object, reason codes, exit statuses, exception boundary.
- [x] B032 Tests T1, T17 to T23, T25, T26, T33, T34, T44 to T48, T53, T54.

### B4 generation

- [x] B040 Exclusive temporary file, no-replace atomic publication, capability detection and `filesystem_unsupported`, file and directory `fsync`, cleanup (spec 9.1).
- [x] B041 Tests T27 to T31 and T37 to T41 using real subprocesses, SIGKILL at controlled points and fault injection at the pre-publication steps and the directory flush; T51.
- [x] B042 Informational `notes` field and tests T42, T43 (spec 7.3.1).
- [x] B043 Test T32 (point-in-time limitation demonstration).

### B5 drill and documentation

- [x] B050 Extend `scripts/test-db-restore.sh` with the real-dump drill of spec 11.3 using a synthetic key; state the limits of spec 11.8 in the drill log. _Evidence: the real `scripts/test-db-restore.sh` ran in hosted Foundation CI run 43643717067 (`postgres` job, hosted PostgreSQL 17 service container, step "Synthetic logical backup and isolated restore") on PR head `b48798875c8a8891b53a7c6dac4697d7641a0fd6`. The recovery-set drill passed its valid-set verification, six negative classes and three different-installation rejection checks (second synthetic installation with a distinct UUID, positive control passed), and the restored schema head and installation identity assertions passed. This is synthetic CI evidence only; it is not real NAS recovery, independent verification, clean-host recovery or RPO/RTO evidence._
- [x] B051 Documentation page (integrity, authenticity, freshness and expectations; trust inputs; generation-host trust boundary; HMAC limitation; filesystem assumptions; custody responsibilities) and cross-references, with no status change.
- [x] B052 Quality gates, mutation checks of plan 1.4, hosted CI on the PR head and, separately, on the merge commit. _Evidence: local quality gates and mutation checks were completed and reported; hosted PR-head Foundation CI run 43643717067 passed all six jobs (scope, backend, postgres, containers, frontend, ci), with none skipped or cancelled, and its hosted PostgreSQL job ran the synthetic logical backup and isolated restore drill successfully. Hosted merge-commit Foundation CI run 43647391844, attempt 3, completed successfully on exact merge commit `47b949e61c96a2e3c2fd883e1784a2856946146c`: all six jobs (scope, backend, postgres, containers, frontend, ci) passed, with none skipped, cancelled or failed; the PostgreSQL integration tests and synthetic logical backup/isolated restore step passed, as did the container tests and aggregate CI gate. This is synthetic CI evidence only and does not establish real NAS recovery, independent verification, clean-host recovery, RPO/RTO or recovery readiness._

## Phase C: before any real-key or real-set use (design, preparation and non-operational implementation authorized; operational work not authorized)

Authorization boundaries, from three separate owner decisions of 15 November 2026: (1) Phase B was formally accepted (synthetic-only scope); (2) Phase C design and documentation work was authorized; (3) a subsequent, separate owner decision authorized implementation of the non-operational portions of C1 to C5. The third decision does not authorize real-key operations, key-custody activation, NAS or production-storage access, recovery operations, capacity measurements, synthetic-key governance or capacity demonstrations, or any claim of operational readiness:

| Category | State |
|---|---|
| Authorized | Design, policy-drafting and requirements work for C1 to C5, and implementation of their non-operational portions: record validators, report-only reconciliation, a model-only capacity calculation and interface definitions in `backend/app/recovery_governance` (see [RECOVERY_PHASE_C_IMPLEMENTATION.md](../../docs/RECOVERY_PHASE_C_IMPLEMENTATION.md)). C5 stays requirements and interface preparation only |
| Pending owner approval | Every Phase C proposal and design (roles, storage design, hash-governance option, retention periods, capacity thresholds, key-generation requirements). A proposal is not a decision |
| Not authorized: measurements and tests | Capacity measurements, large-data runs, NAS or production-storage access, and synthetic-key test runs for governance or capacity demonstrations |
| Not authorized: operations and key tooling | Key-generation or key-management tooling, generating, provisioning, storing, rotating or activating a real key, custody activation, creating or operating a real recovery set, operational recovery or restore, and any migration, schema or configuration change |

The Phase C design/preparation drafts were delivered in documentation-only [PR #42](https://github.com/LYF-FC/local-assistant-core/pull/42) (merge `b081c12`): C1 [key custody and key-generation requirements](../../docs/RECOVERY_KEY_CUSTODY.md), C2 [expected-hash governance](../../docs/RECOVERY_HASH_GOVERNANCE.md), C3 [retention and forgetting](../../docs/RECOVERY_RETENTION.md), C4 [capacity-validation plan](../../docs/RECOVERY_CAPACITY_VALIDATION.md), and C5 requirements preparation within the key-custody draft. The independent-verification document was delivered in PR #42 as a blank record template and has since been replaced on `main` by a populated record (see below). The four design/preparation drafts (C1 to C4, with C5 requirements inside the C1 draft) are proposals/preparation artifacts only; no proposal has been approved, and no proposal's status is changed here. C4 measurements and a ceiling decision have not occurred. PR #42 delivered design and preparation drafts only. Separately, on 15 November 2026 the owner authorized implementation of the non-operational portions of C1 to C5, and that implementation was merged in [PR #43](https://github.com/LYF-FC/local-assistant-core/pull/43) (merge `708e8134098846a40e0c49cae5a954913aef9fdb`; see [RECOVERY_PHASE_C_IMPLEMENTATION.md](../../docs/RECOVERY_PHASE_C_IMPLEMENTATION.md) and [DECISIONS.md](../../DECISIONS.md)). It does not complete any Phase C task: all C1 to C5 checkboxes below remain unchecked, because the owner decisions, measured evidence and operational outcomes they require do not exist. Design authorization, non-operational implementation authorization, operational authorization, independent verification and owner acceptance remain distinct. Only design and non-operational implementation authorization have been granted; completion of independent verification is not established by the populated record, and Phase C acceptance and operational authorization remain absent. No synthetic-key governance or capacity test, key operation, NAS or production-storage access, capacity measurement or operational recovery was performed or authorized.

The non-operational implementation does not complete any task below: the owner decisions, measured evidence and operational outcomes they require do not exist. The boxes below stay unchecked: PR #42 delivered drafts and PR #43 delivered bounded non-operational implementation; neither supplies the owner decisions, measured evidence or operational outcomes represented by these tasks. Delivery and implementation do not complete a task.


- [ ] C1 Key holder, custody, storage, access, backup and loss-recovery procedure (O1b). Draft proposal delivered in PR #42; non-operational validators/model/interface work merged in PR #43. Owner decision, custody activation and operational procedure remain open.
- [ ] C2 Governance of the independently retained expected manifest hash (O5). Draft proposal delivered in PR #42; non-operational record-validation/reconciliation code merged in PR #43. Owner decision and independent expected-hash governance remain open.
- [ ] C3 Retention policy for manifests, backups and archives, expected-hash records, and forgetting reconciliation (O2). Draft matrix delivered in PR #42; non-operational retention validators/report-only reconciliation merged in PR #43. Every retention duration and policy decision remains open.
- [ ] C4 Measured resource testing and a separate owner decision on the real operational dump ceiling (O8); 64 GiB is not approved. A validation plan and model-only capacity calculation were delivered in PRs #42–#43; no measurement or ceiling decision has occurred, and measurement remains unauthorized.
- [ ] C5 Key-generation requirements and design preparation only (O9). Requirements/interface preparation is in PR #42 and non-operational interface definitions merged in PR #43; key-generation tooling and any provisioning workflow remain unauthorized and deferred until custody is decided.

Independent-verification record (not a Phase C task and not a checkbox): a populated record, [RECOVERY_INDEPENDENT_VERIFICATION.md](../../docs/RECOVERY_INDEPENDENT_VERIFICATION.md), was committed in `1233a914dddecb9a63eb03df129e72b731260710` for verification revision `519cc2d911e2ded192dab2e3c87a125478bb7240` (spec section 11.7, step 3). It is prepared from human-reviewer confirmations and inspected CI evidence. Criterion-level source/test/result traceability and the identified evidence gaps remain to be reconciled (see [RECOVERY_INDEPENDENT_VERIFICATION_TRACEABILITY.md](../../docs/RECOVERY_INDEPENDENT_VERIFICATION_TRACEABILITY.md), supplementary and not the reviewer's record). The record's existence does not establish completion of independent verification. C1 to C5 remain unchecked, Phase C remains unaccepted, and no operational authorization exists; the prohibitions on real-key, real-set, production-storage and operational-recovery activity remain in force.

## Not tasks of this spec

Restoration and staging (a later restore specification, including database binding of the installation identity and restore from the exact verified staged copy); approved-job and reminder-worker process-kill tests (a later, separate specification, O4); encryption; backup scheduling or freshness services; DOC-X02; worker liveness; RPO/RTO acceptance; clean-host rehearsal.
