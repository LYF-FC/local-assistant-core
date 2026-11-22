# Spec 074 — human reviewer handoff and current-main refresh

**Current review preparation:** use [section 7](#7-current-main-review-refresh--22-november-2026) for the explicitly refreshed target. Sections 1–6 preserve the historical `1c94e445` packet; their target, pending statements and links are historical, not current-main instructions.

**Preparation only; every reviewer action below is pending.** This assistant-prepared
handoff identifies the merged source and the bounded review needed next. It is not
a reviewer record, independent verification, acceptance of Spec 074 or any gate,
or authorization for a key, set, measurement or recovery operation.

## 1. Exact target and normative text

Review **main `1c94e445db3dcc74a0133813b35300d205a64380`**, the merge of
[PR #54](https://github.com/LYF-FC/local-assistant-core/pull/54). The reviewed PR
head and integration head are historical identities, not substitutes for this
merge revision. A later documentation head must not silently replace this target.

The [specification at this target](https://github.com/LYF-FC/local-assistant-core/blob/1c94e445db3dcc74a0133813b35300d205a64380/specs/074-recovery-set-manifest/spec.md)
contains the original 14 November freeze at
`f903237a69e6e2eeeef8b057abef3fc618a27630` **plus two separately recorded,
owner-approved post-freeze clarifications**:

| Clarification | Current normative requirement | Review boundary |
|---|---|---|
| 16 November 2026, T25 | The key's installation binding is checked before key references and the MAC. Installation A's key with B's manifest yields `key_installation_mismatch`. | Confirm the exact test assertions against the corrected row; do not reopen the owner's wording decision. |
| 17 November 2026, A5 / stage-1 overlap | Missing/malformed shapes and parser errors still cause zero filesystem access. Only after all required shapes are valid may the overlap pre-check use path-component `lstat`/`readlink` and same-file `stat` metadata for overlap/alias detection. No open, content read, enumeration, mutation or publication is permitted during that check. | Confirm the implementation and focused guards satisfy that narrow exception. Wording approval is not acceptance of implementation or A5. |

The original freeze reference/date are preserved. The current spec is deliberately
not byte-identical to the original freeze. See [the decision log](../DECISIONS.md)
and [spec sections 2.5, 7.1, A5 and T25](../specs/074-recovery-set-manifest/spec.md).
PR #54 records clarification and test evidence, not a runtime change.

### Selected source identities

The following SHA-256 values were read from the target files during preparation;
they are source-identity evidence, not execution results. Recheck them before review.

| File | SHA-256 at `1c94e445` |
|---|---|
| `specs/074-recovery-set-manifest/spec.md` | `79d6f80dc99bc3ed450ddfa3329a21a76f017ae1ba5cf11867bc29a4c4b666b1` |
| `backend/app/recovery_set/cli.py` | `94d147c0a119a8fe202527825f69112befbad61c2d6bb364d44ba18961785ee0` |
| `backend/tests/test_recovery_set_overlap_metadata.py` | `093d32af24b8d318e8fc6f59462a2e7bf82b239445cae05296d0ddbe279d0391` |
| `backend/tests/recovery_set_support.py` | `a54fd797f296aef70e615413f338b7e712d468ab7e90234701da01bd7c770fa7` |
| `backend/tests/test_recovery_set_verify.py` | `a7385b49dbebf414f0b28dc82a202a1d2d144bc670b3f7a9d2e7da0dd250fcc8` |

Git tree objects at this target: `backend/app/recovery_set` =
`31107a8ac40ac86fe0b69fe0e7fe5f718165982b`; `backend/tests` =
`4cf3cb552e5fe55443dfd964bd10d0889fd2b8af`; `specs/074-recovery-set-manifest` =
`d2b7624997470cabc454762e4524d1ef95c65dfc`.

Read-only identity checks may use `git rev-parse HEAD`, `git status --short`,
`git show 1c94e445db3dcc74a0133813b35300d205a64380:<path>` and independent hashes.
Keep dirty working-tree files separate from the immutable Git objects being reviewed.

## 2. Evidence classes and historical records

| Evidence | Revision / attribution | How the reviewer should use it |
|---|---|---|
| [Original human record](RECOVERY_INDEPENDENT_VERIFICATION.md) | `519cc2d911e2ded192dab2e3c87a125478bb7240`, 15 November; human-reported confirmations | Preserve it unchanged. It is not a human review of `1c94e445`. Do not relabel its M1–M12/U1–U3 or reviewer-run checks as assistant-observed execution. |
| [Criterion index, appendix section 8](RECOVERY_INDEPENDENT_VERIFICATION_TRACEABILITY.md) | Assistant-prepared index for `48c358136564b4a8362887f48cd8ac619a732c9d` | Reuse the A/T mapping as an index to inspect, not as a new verdict for every row at this target. Keep earlier source/run attribution. |
| Appendix section 11 | PR #54's metadata-exception tests, guard corrections and local named results | Inspect the final 248-case file and nine sensitivity-control cases, not only the earlier 241-case version. Preserve root/unprivileged environments and guard limitations. |
| Full hosted CI at the present target | [Foundation CI #187, run 44382004350](https://github.com/LYF-FC/local-assistant-core/actions/runs/44382004350), verified `push`, attempt 1, head `1c94e445db3dcc74a0133813b35300d205a64380` | Check the run identity and final six job results directly. This handoff does not assert run completion or a passing final result. Record only inspected results. |
| Historical hosted CI | Prior PR, merge and manual runs retain the SHAs recorded in the appendix/master | Their passes, skips and failures remain historical. Neither matching trees nor advisory withdrawal transfers a result to this merge revision. |

The appendix's earlier advisory-blocker sentence and failed CI descriptions are
historical observations from their recorded runs. The subsequent advisory withdrawal
is recorded in the [later decision](../DECISIONS.md) and [resumption plan](MVP_RESUMPTION_PLAN.md).
No audit exception was activated, and withdrawal is not a source-code fix. Read
the actual ordinary audit result on the target's CI rather than inferring success.

## 3. V1–V13 at this target — all pending human review

Use the existing [appendix section 9 checklist](RECOVERY_INDEPENDENT_VERIFICATION_TRACEABILITY.md#9-reviewer-checklist-pending-human-review)
without ticking or rewriting it in this preparation. The table below adapts its
entry points to the now-merged clarifications; it does not supersede the full
54-row T index or A1–A13 index.

| Item | Pending action at `1c94e445` | Required reviewer output |
|---|---|---|
| V1 — source identity | Check the exact commit, selected hashes and tree objects above; distinguish all historical verification revisions. | Actual source identity and any mismatch/dirty-tree qualification. |
| V2 — A5 parser | Read [`parse_arguments` and `_option_like`](https://github.com/LYF-FC/local-assistant-core/blob/1c94e445db3dcc74a0133813b35300d205a64380/backend/app/recovery_set/cli.py#L48) and [`test_the_closed_parser_agrees_with_the_argparse_parser_it_replaced`](https://github.com/LYF-FC/local-assistant-core/blob/1c94e445db3dcc74a0133813b35300d205a64380/backend/tests/test_recovery_set_verify.py#L844). | Findings on zero-access parsing and the documented `--` narrowing; do not infer arbitrary parser equivalence. |
| V3 — A5 / T36 metadata exception | Inspect the focused evidence path in section 4 below against the merged exception, `_spellings`, `_same_existing_file` and `_overlaps`. | Whether assertions substantiate the approved bound, and every remaining limitation or contradiction. No acceptance of A5 is prefilled. |
| V4 — T7 containment | Read [`test_t7_unsafe_member_paths_cannot_reach_outside_the_set` and its escape control](https://github.com/LYF-FC/local-assistant-core/blob/1c94e445db3dcc74a0133813b35300d205a64380/backend/tests/test_recovery_set_format.py#L246). Distinguish explicitly supplied trust-input paths from an attempted escape. | Assertion-level containment findings, including the guard's scope. |
| V5 — T25 | Read [`test_t25_cross_installation_substitution`](https://github.com/LYF-FC/local-assistant-core/blob/1c94e445db3dcc74a0133813b35300d205a64380/backend/tests/test_recovery_set_verify.py#L250), all three exact outcomes and the same-installation control against the corrected row. | Confirmation or contradiction at assertion level, including reason, exit and four states. Historical comments still describing an open conflict are not authority over the merged decision. |
| V6 — T27 | Read [`test_t27_kill_after_publication_before_the_directory_flush`](https://github.com/LYF-FC/local-assistant-core/blob/1c94e445db3dcc74a0133813b35300d205a64380/backend/tests/test_recovery_set_publish.py#L109). Check `after_link` versus `after_publish`/`before_dir_fsync`, preservation before deliberate cleanup, retry and verification. | Findings on bytes, inode/link counts, leftover preservation, `output_exists`, notes and single-link rejection. Keep process/fault-interface limits explicit. |
| V7 — T33 / A8 | Read the disclosure tests in `test_recovery_set_verify.py`: `test_t33_key_material_never_appears`, `test_t33_key_material_is_absent_from_generate_output_and_files`, `test_t33_application_logs_never_contain_key_material`. | Exact streams/forms checked and exclusions; in-process log capture is not proof about every subprocess, logger or native interface. |
| V8 — A11 / A12 | Inspect the Work suppression/auth and downgrade pointers in the original V8 entry and the current target's relevant sources. The original empty-diff claim and counts belong to their named revisions. | Current source/diff basis and whether historical evidence is accepted for the stated scope; no inherited current pass. |
| V9 — A13 document review | Read the documents listed in section 5; automated limit tests do not discharge the document-review clause. | Document-level findings and any remaining unsupported capacity, timing or readiness claim. |
| V10 — exact-revision full coverage | Read CI #187's head/event/attempt and final `scope`, `backend`, `postgres`, `containers`, `frontend`, `ci` results. Inspect relevant logs and distinguish job success from per-case evidence/skips. | The actual coverage basis and the reviewer's judgement against spec 11.7 step 3. In-progress or scope-reduced results cannot be recorded as full coverage. |
| V11 — privilege-dependent cases | Read T6 device-node, T13 unreadable-key and T31 read-only-output tests and their skip conditions; keep the historical root/unprivileged results separate. | Whether recorded complementary runs are accepted or further authorized evidence is needed; no unnamed hosted progress marker is a named device-node pass. |
| V12 — criterion index sample | Re-read cited bodies for at least T7, T25, T27, T33, A5, A10, A13 and the new overlap delta; spot-check other indexed rows. | Corrections to any assertion note that does not match the target; no replacement of 54-row coverage by this short list. |
| V13 — new reviewer record | A human reviewer distinct from the implementation agent records actual revision, evidence read, checks personally performed, findings and unresolved matters in a new record. | Human-confirmed findings with limits; this preparation supplies neither signature nor conclusion. Preserve the `519cc2d` record. |

## 4. Focused A5 / T36 reading route

The [248-case guard file](https://github.com/LYF-FC/local-assistant-core/blob/1c94e445db3dcc74a0133813b35300d205a64380/backend/tests/test_recovery_set_overlap_metadata.py)
is a focused delta to the existing criterion index. Read these mechanisms together:

| Evidence path | Assertion to inspect |
|---|---|
| `strict_zero_access`; missing/malformed/freshness-without-hash cases, lines 264–312 | No recorded read-side or mutation-side calls; exit 2 with the exact reason and all four states not evaluated; output directory unchanged. These include overlapping supplied paths and five locale environments. |
| `test_a_the_overlap_precheck_runs_only_after_every_shape_is_valid`, line 315 | The pre-check is not reached for invalid shapes, but is reached for valid overlapping and non-overlapping input. |
| `expected_metadata_targets`, line 99; `assert_metadata_only`, line 142 | The expected exact targets are prepared before recording, without using the implementation's overlap helpers or `realpath`. Recorded calls cannot enlarge the allowlist. Check helper, operation and literal target, including symlink chains and non-normalized spellings. |
| `test_a_overlap_rejection_is_paths_overlap_and_only_reads_metadata`, line 346 | Fourteen overlap mechanisms; `paths_overlap`, exit 2, all states not evaluated, no mutation, unchanged filesystem snapshot and no publication. Metadata activity must actually be observed. |
| `test_a_symlink_resolution_and_same_file_comparison_are_the_permitted_operations`, line 363 | Symlink resolution and hard-link alias comparison exercise the permitted kinds; this does not grant metadata permission to unrelated targets. |
| `test_a_valid_non_overlapping_inputs_still_read_through_the_protected_path`, line 378; durable-generation case, line 411 | Both successful `generate` and `verify` scope the guard to the pre-check, then reach protected content reads. Generation still publishes durably afterward. A zero-call test caused by never reaching the implementation is insufficient. |
| Nine sensitivity-control cases, lines 430–573 | Content read, enumeration, write, early metadata, early `utime`, unrelated targets inside an approved helper, same-file probing of SET, and lexical-only alias detection must be caught by the intended assertions. |

Read the common [`file_access_guards`](https://github.com/LYF-FC/local-assistant-core/blob/1c94e445db3dcc74a0133813b35300d205a64380/backend/tests/recovery_set_support.py#L218)
and `mutation_guards` as well. These are Python-level observations, not syscall
interception or a sandbox. Pre-bound references, native/`ctypes` operations,
import/fixture preparation and unlisted operations remain outside the guards.
The fixture snapshot/target expectation provides no race protection and proves
nothing about operational storage or a real recovery host.

For T25, the expected reasons are exactly `installation_mismatch`,
`key_installation_mismatch`, then `key_fingerprint_mismatch` in the three scenarios.
The first has valid integrity/authenticity and unmet expectations; the latter two
have invalid authenticity and other states not evaluated. Read the explicit
`notes`, `verified_references` absence and exit assertions too. The same-installation
control preserves reachability of `manifest_key_reference_mismatch`. The test's
old conflict prose is historical/stale; the two merged spec clarifications govern.
A comment-only reconciliation can be proposed separately for that stale prose;
no assertion or runtime correction is implied, and no test is edited in this batch.

## 5. A13 reading and environment limitations

Read [capacity validation](RECOVERY_CAPACITY_VALIDATION.md),
[the operator guide](RECOVERY_SET.md), [Phase C implementation](RECOVERY_PHASE_C_IMPLEMENTATION.md),
[the appendix](RECOVERY_INDEPENDENT_VERIFICATION_TRACEABILITY.md) and
[the master](../PROJECT_MASTER.md) at the target. Specifically look for:

- A provisional limit or the **unapproved 64 GiB** placeholder described as validated capacity.
- A synthetic verification/drill time described as RPO, RTO or recovery readiness.
- A small injected-limit test described as a large-data/capacity measurement.
- M5 above-limit metadata rejection confused with below/equal-limit hashing.
- A record validator, model-only calculation or approved wording described as
  operating custody, an approved policy, independent verification or permission to restore.

Record which documents were actually read. Do not substitute a string search or
passing unit tests for this clause's human review.

Privilege pointers: [`test_t6_device_node_member_is_rejected`](https://github.com/LYF-FC/local-assistant-core/blob/1c94e445db3dcc74a0133813b35300d205a64380/backend/tests/test_recovery_set_fsset.py#L162),
[`test_t13_unreadable_key_file_is_unsafe`](https://github.com/LYF-FC/local-assistant-core/blob/1c94e445db3dcc74a0133813b35300d205a64380/backend/tests/test_recovery_set_format.py#L471),
and [`test_t31_read_only_output_directory`](https://github.com/LYF-FC/local-assistant-core/blob/1c94e445db3dcc74a0133813b35300d205a64380/backend/tests/test_recovery_set_publish.py#L233).
Device-node creation needs privilege; root bypasses the two permission-denial cases.
Earlier runs passed complementary cases in different modes. A pass in one mode
does not imply that all cases ran there or on the current hosted runner.

## 6. Next bounded validation and closure boundary

1. The human reviewer establishes the exact target and reads the normative delta,
   source assertions and final exact-target CI evidence. No new runtime test,
   synthetic-key run or capacity campaign is performed by this preparation.
2. The reviewer records pending V1–V13 findings, including any need for additional
   execution evidence. Any proposed run must identify its environment, scope and
   existing authorization or seek separate authorization where required; do not
   silently turn this handoff into permission for measurements or key operations.
3. The owner reviews the separate [C1–C5 decision worksheet](SPEC_074_OWNER_DECISION_WORKSHEET.md).
   Criterion coverage and policy/operational decisions are different work: a
   successful human review does not tick C1–C5, approve a dump ceiling or activate custody.
4. The owner determines the remaining bounded Spec 074 MVP closure work from those
   findings and decisions. This handoff cannot declare the whole specification
   complete while its independent-review and deferred-matter prerequisites remain.
   C1–C5 are not silently moved to a later release by the tooling deferral.
5. Only after that bounded Spec 074 closure/review step should the reserved Spec 075
   contract be prepared. Restore/staging, restored-database installation binding,
   older non-Work reconciliation and clean-host/RPO/RTO acceptance remain the later
   contract/gate scope. Spec 075 implementation is not a prerequisite for doing
   this Spec 074 source review, and this review is not evidence that Gate 11 is complete.

Spec 11.7 keeps implementation, independent verification, owner decisions,
the later restore gate and environment/scope-specific acceptance separate.
No frozen text, historical reviewer record, existing checkbox, acceptance or
operational status is changed by this handoff. The [master](../PROJECT_MASTER.md)
remains the authority for current scope and evidence.


### Later design decision outside the pinned source target

On 18 November 2026 the owner approved C1–C3 design baselines, C4 planning only
and C5 manual-ceremony requirements; see [the decision](../DECISIONS.md#18-november-2026--spec074-c1c3-design-c4-planning-and-c5-manual-ceremony-requirements-approved).
The worksheet now distinguishes approved design choices from pending details.
This is not a human verification result, a task/acceptance promotion or a change
to the immutable `1c94e445` review target; no operation or measurement is authorized.


## 7. Current-main review refresh — 22 November 2026

**Project context:** Butler’s north star is MVP-01: a coherent, usable end-to-end user journey. This packet covers the bounded Spec 074 review; for project-wide batch and journey guidance, see [orchestration instructions](project-orchestration/instructions.md). This review does not change priorities or constitute owner acceptance.

**Assistant preparation only. Human V1–V13 findings/sign-off remain pending.**
This section explicitly refreshes the review target; it does not rewrite the historical
packet, the original human record or the appendix checklist. No criterion, C1–C5 task,
MVP gate, independent verification or acceptance is promoted. PROJECT_MASTER and
DECISIONS remain authoritative. The owner's instruction for this batch is to compare
current main, identify reusable/missing evidence and prepare this human handoff.

### 7.1 Exact source and local delivery identity

- Repository: `LYF-FC/local-assistant-core`; remote: <https://github.com/LYF-FC/local-assistant-core>.
- Historical pinned comparison base: `1c94e445db3dcc74a0133813b35300d205a64380` (PR #54).
- Refreshed immutable review target and local branch base:
  [`01e6fb5f7f2947fae7c38ea1b9c0200e19bc7162`](https://github.com/LYF-FC/local-assistant-core/commit/01e6fb5f7f2947fae7c38ea1b9c0200e19bc7162)
  (PR #71 merge; live main checked on 22 November 2026).
- Dedicated local branch: `work/spec074-review-refresh/a1-review-handoff`.
- Delivery change: `docs/SPEC_074_REVIEW_TARGET_1C94E445.md` only. The owner subsequently
  authorized committing this packet locally. The containing Git commit identifies
  the delivery revision; obtain its full SHA with `git log -1 --format=%H --
  docs/SPEC_074_REVIEW_TARGET_1C94E445.md`. That delivery revision is separate from
  the immutable runtime review/CI target above. At the time this handoff was prepared, it had not been pushed or submitted as a PR. It was later published with owner authorization in [PR #72](https://github.com/LYF-FC/local-assistant-core/pull/72); the review target above remains unchanged. Publication does not constitute reviewer sign-off or owner acceptance.
- The unrelated dirty `codex/approval-review-inbox` checkout was preserved.

Before review, re-query main and pin the actual revision. If it moved, inspect the
additional delta; do not silently retarget this packet or transfer execution results.
Review source at the immutable target; keep the handoff delivery revision separate.

### 7.2 Delta since the pinned target

The Git comparison contains 41 changed/added paths. Obtain the complete exact inventory
with `git diff --name-status 1c94e445db3dcc74a0133813b35300d205a64380 01e6fb5f7f2947fae7c38ea1b9c0200e19bc7162`;
read the full diff, not only the summary below.

| Change | Consequence for review |
|---|---|
| Spec 074 implementation tree `backend/app/recovery_set` unchanged, tree `31107a8ac40ac86fe0b69fe0e7fe5f718165982b`; frozen `spec.md`, guard support and overlap tests byte-identical | Reuse source navigation and A/T mapping after checking identities. The parser and metadata exception still need human judgement; unchanged bytes are not a fresh test pass. |
| PR #67: T25 docstring/comment correction in `backend/tests/test_recovery_set_verify.py` | The file AST excluding docstrings is identical across the comparison. Assertions/runtime did not change. Read the corrected explanation; section 4's suggestion to correct stale T25 prose is now historical and no longer a next action. |
| PR #57: owner C1–C3 design baselines, C4 planning-only and C5 manual requirements; worksheet/task/policy wording | Re-read DECISIONS, worksheet, custody/hash/retention/capacity/Phase C documents. Design approval does not complete C1–C5, activate custody or authorize a run. |
| PR #58: C4 pilot and manual-ceremony proposals | Include both new documents in V9/A13. Numeric budgets and ceremony execution remain proposals; 64 GiB is unapproved. |
| PR #59: `recovery_staging.py`, `recovery_staging_binding.py`, unit/integration tests, `recovery-staging-fixtures.py`, Spec 075 contract artifacts; three added lines in `test-db-restore.sh` | New consumer imports Spec 074 helpers and `verify`; shared restore drill now runs a dump-only staging subdrill. Review the integration boundary and current drill logs. Do not convert this into whole-Spec-075 review/completion. Results stay quarantined; non-Work reconciliation and archive staging remain absent. |
| PR #68: six leakage harness/test files plus master evidence wording | Test-only Gate 1 evidence and shared-suite workload changed. Thirteen operations and discovery boundary placement remain uncovered. This does not verify Spec 074 or accept a gate. |
| PRs #60–#65 and #67: master/register/resumption/history/traceability reconciliation; PR #62 isolated picomatch research protocol; PRs #69–#71 orchestration guidance | Re-read current authority and use the structured branch/evidence rules. Research is non-blocking and permits no dependency implementation. Historical “current” wording retains its original SHA attribution. |
| Dependency locks, manifests, CI workflow, migrations, Spec 074 governance implementation/tests and Work suppression paths unchanged | Existing review navigation remains useful. Full current-target execution, audit results and current reviewer conclusions are still needed; no inherited pass. |

Current SHA-256 values (source identity only):

| File | SHA-256 at refreshed target |
|---|---|
| `specs/074-recovery-set-manifest/spec.md` | `79d6f80dc99bc3ed450ddfa3329a21a76f017ae1ba5cf11867bc29a4c4b666b1` |
| `backend/app/recovery_set/cli.py` | `94d147c0a119a8fe202527825f69112befbad61c2d6bb364d44ba18961785ee0` |
| `backend/tests/test_recovery_set_overlap_metadata.py` | `093d32af24b8d318e8fc6f59462a2e7bf82b239445cae05296d0ddbe279d0391` |
| `backend/tests/recovery_set_support.py` | `a54fd797f296aef70e615413f338b7e712d468ab7e90234701da01bd7c770fa7` |
| `backend/tests/test_recovery_set_verify.py` | `a12fe45cc70ec30df87425880e502c27e7553d854c3d6075acecd33f769a4ccf` |
| `scripts/test-db-restore.sh` | `bec578444f08c6a933f8ccbccf505cd05480d4201a17c1f2648fbf679c6aeac7` |

### 7.3 Reusable evidence and explicit gaps at the initial refresh

| Evidence inspected live during refresh | Use and limits |
|---|---|
| [CI #187 / 44382004350](https://github.com/LYF-FC/local-assistant-core/actions/runs/44382004350), pinned `1c94e445` | All six job conclusions inspected: success. Reusable historical exact-revision job evidence; this refresh did not inspect its case-level logs or establish human verification. |
| [Merge CI 44945063242](https://github.com/LYF-FC/local-assistant-core/actions/runs/44945063242), `677298f310832abdcc31390bac5aec51d2012843` | All six jobs success. Backend log: 2860 passed, 1 skipped, 1197 deselected; PostgreSQL: 1197 passed, 2861 deselected. Recovery log: valid set, six negative classes, three different-installation checks; new staging subdrill reports exact-byte restore after source mutation, identity/schema mismatch and invalid-dump refusal, quarantine. These are historical synthetic results, not current-tip results or RPO/RTO. |
| [Current-main CI #224 / 45003682052](https://github.com/LYF-FC/local-assistant-core/actions/runs/45003682052), exact refreshed target, push, attempt 1 | Completed success; scope and ci passed, backend/postgres/frontend/containers skipped. The API listed only this run at the target during refresh. Full current-target coverage is missing. |
| Original human record at `519cc2d`; assistant criterion index at `48c3581`; final PR #54 overlap evidence | Preserve attribution and use as reading guides. No current-revision human criterion-level record/sign-off has been established. All existing human checklist boxes remain untouched. |
| Privilege-dependent T6/T13/T31 | The historical merge log has an unnamed skip in `test_recovery_set_fsset.py`; its identity is not established from progress markers. A named current-target device-node pass is missing. Root and non-root outcomes must be distinguished. |
| Spec 075 convergence record | Retain its recorded broad local failures and successful targeted reruns separately. Later hosted successes do not explain the original unresolved causes or certify clean-host recovery. |

Missing evidence includes current-target full coverage, named privilege-case outcomes
or explicit human disposition of historical runs, the human V1–V13 findings and actual
reviewer identity/revision, A13 document judgement, remaining C1–C5 details/measurements,
and independent host/provider/recovery evidence. The latter operational gates are not
execution tasks authorized by this refresh.

### 7.4 Exact checks needed — initial execution plan

The initial plan below predates the separately authorized full-CI execution in section 7.6.
Read that later evidence before treating a planned check as still missing.

Use a clean Linux synthetic test checkout at the exact target. Spec 074 protected-path
and staging behavior requires Linux `O_PATH`; the local macOS documentation checkout
is not equivalent runtime evidence. Use Python 3.12, uv 0.13.4, Node 22 and locked
dependencies. Follow [TESTING](TESTING.md) and the unchanged CI workflow.

1. **Identity and delta:** `git rev-parse HEAD`; `git status --short`;
   the full comparison in 7.2; `git rev-parse HEAD:backend/app/recovery_set`;
   independently hash the six files above. Compare Work/migrations explicitly:
   `git diff 1c94e445db3dcc74a0133813b35300d205a64380 01e6fb5f7f2947fae7c38ea1b9c0200e19bc7162 -- backend/alembic backend/tests/test_work_suppression_auth.py backend/tests/test_work_suppression_file.py backend/tests/integration/test_work_suppression_postgres.py` (expected empty).
2. **Full exact-target hosted coverage:** run the existing Foundation CI manual
   workflow at main only while main still equals the target (`gh workflow run ci.yml
   --repo LYF-FC/local-assistant-core --ref main`). This is a proposed dispatch,
   **not performed by this preparation**. Check returned run head SHA, event, attempt
   and final six jobs: `scope`, `backend`, `postgres`, `containers`, `frontend`, `ci`.
   Every product job must execute successfully; retain failures/cancellations and
   named skips. If main moved, a run at the newer SHA cannot satisfy this target.
   Do not alter selection or workflows. A Markdown-only handoff PR's narrow run
   would validate that edit only.
3. **Required job contents:** backend: locked sync, Ruff check/format, full
   non-integration pytest with coverage, Bandit, pip-audit and repository policy;
   frontend: locked npm install, complete tests/build and high-threshold audit;
   PostgreSQL 17: full integration suite as configured, real restricted-role and
   migration/downgrade checks, then `bash scripts/test-db-restore.sh` including the
   Spec 074 negatives, Spec 075 subdrill and existing archive/Work restoration;
   containers: complete `bash scripts/test-containers.sh`, including HTTPS/browser
   and recovery phases. Use the workflow's disposable guards, identities and service
   setup; do not run restore scripts against an owner DB or trust store. `make check`
   alone omits PostgreSQL, audits and the complete container/recovery evidence.
4. **Named focused diagnostics**, from `backend/` after locked sync in the disposable
   Linux environment: `uv run --locked pytest tests/test_recovery_set_*.py -m 'not integration'
   --allow-unix-socket -vv -ra --junitxml=/tmp/spec074-review.xml` and
   `uv run --locked pytest tests/test_recovery_set_overlap_metadata.py -k control -vv -ra`.
   Inspect T7, T25, T27, T33, parser and overlap assertions, all A1–A13/T1–T54 index
   rows and all nine overlap sensitivity controls. Do not predeclare historical counts
   as current outcomes. Focused runs supplement, never replace, full coverage.
5. **Complementary privilege evidence:** in an explicitly disposable Linux environment
   with device-node capability, run
   `uv run --locked pytest tests/test_recovery_set_fsset.py::test_t6_device_node_member_is_rejected -vv -ra`.
   In a separate non-root process with writable synthetic scratch, run
   `uv run --locked pytest tests/test_recovery_set_format.py::test_t13_unreadable_key_file_is_unsafe tests/test_recovery_set_publish.py::test_t31_read_only_output_directory -vv -ra`.
   Record UID, capabilities, Python/platform/filesystem and each node ID/result. A skip
   is a gap. If reruns are unavailable, the human reviewer must explicitly assess the
   recorded complementary historical runs and their limits; never infer their acceptance.
6. **A11/A12 and consumer boundary:** inspect unchanged Work suppression/auth and
   migration paths and their full-suite results. Inspect the changed restore harness
   and new staging imports/negative tests as the consumer delta; identify the exact
   dump-only scope and preserve quarantine. No archive-staging or non-Work forgetting
   claim follows. Any additional execution uses only authorized synthetic fixtures.
7. **Human document review:** apply V9/A13 to all five documents in section 5 plus
   current DECISIONS, owner worksheet, custody/hash/retention documents, C4 proposal,
   manual-ceremony proposal and Spec 075 scope/convergence. Record actual readings and
   findings, including stale “current” statements, claimed source reviews without
   records, unapproved ceilings, synthetic timings and old sequencing prose.
8. **Human return:** use existing V1–V13 labels and original A/T index, record criterion,
   source line, exact revision, evidence/run/node ID, expected versus observed result,
   severity, coverage limits and unresolved decision. Leave the `519cc2d` record and
   existing checkboxes unchanged in this preparation. Human findings/sign-off and
   owner acceptance are separate later records/decisions.

### 7.5 Preparation validation and handoff boundary

Source/diff/hash and AST comparisons were performed locally; GitHub job conclusions
and the historical merge test/drill summaries above were read live. Documentation
validation: locked `uv sync --locked --extra dev` succeeded on local macOS/Python 3.13.5;
`backend/.venv/bin/python scripts/check_repository.py` passed;
`backend/.venv/bin/python scripts/test_ci_scope.py` passed all 23 cases and selected
`documentation` for the one changed path;
`backend/.venv/bin/python scripts/build_feature_overview.py --check` verified all
155 references/99 named/155 reviews; `git diff --check` passed. These are
documentation checks only. The initial system-Python attempt lacked PyYAML; offline
locked sync lacked a cached Ruff wheel, so neither attempt is counted as a pass.
Locked dependency installation then succeeded without changing manifests or locks.
No runtime suite,
PostgreSQL restore, privilege test, manual CI dispatch, capacity run, key ceremony,
private-data access or real integration was executed by this preparation. No commit,
push, PR, review submission, merge, release or acceptance was performed.

The human reviewer should begin with 7.1–7.4 and use sections 1–6 only as the historical
reading route. Section 6's contract-only Spec 075 sequencing is superseded by the
separately authorized and merged first slice recorded in the master and DECISIONS.
Resolve the existing review and remaining owner decisions before selecting another
implementation batch; do not create a parallel tracker or duplicate handoff.


### 7.6 Authorized full-CI follow-up — 22 November 2026

The owner subsequently requested full CI on verified current main, log/skip inspection
and an evidence update here, while keeping human verification and owner acceptance
pending. This later execution supersedes section 7.4's “not performed” dispatch
statement and section 7.5's initial preparation-only execution boundary for this run
only; it does not authorize operations, capacity tests or a key ceremony.

- Run: [Foundation CI #225, 45004636677](https://github.com/LYF-FC/local-assistant-core/actions/runs/45004636677).
- Exact head: `01e6fb5f7f2947fae7c38ea1b9c0200e19bc7162`; event `workflow_dispatch`; attempt 1.
- Dispatch command: `gh workflow run ci.yml --repo LYF-FC/local-assistant-core --ref main`.
  Main was checked immediately before dispatch; the returned run head was checked
  afterward and matched. No workflow or required-check changes were made.
- Actual selector output: `mode=full`, all four product jobs enabled; reason
  “Scheduled, manual or unrecognized events require full coverage”. The earlier
  documentation-mode JSON line in the scope log belongs to selector self-tests.

**Final outcome: success.** All six jobs executed and passed; the final gate log
states `CI gate passed for profile: full`. The jobs API reported no skipped or
otherwise non-successful steps. Run completion: 22 November 2026 at 09:09:31 UTC
(10:09:31 Europe/Paris). Main was rechecked after completion and still equalled
`01e6fb5f7f2947fae7c38ea1b9c0200e19bc7162`. There was no retry or changed revision.
This supplies the full exact-target hosted-CI evidence missing at the initial
refresh in 7.3; it does not supply the human V10 judgement or independent verification.

| Job | Exact job ID | Observed evidence |
|---|---|---|
| scope | [137153381016](https://github.com/LYF-FC/local-assistant-core/actions/runs/45004636677/job/137153381016) | Success; policy and 23 scope tests passed; actual profile full. |
| frontend | [137153462451](https://github.com/LYF-FC/local-assistant-core/actions/runs/45004636677/job/137153462451) | Success; 824 tests/33 files passed; build passed; npm audit reported zero vulnerabilities. No test skips reported. |
| backend | [137153462640](https://github.com/LYF-FC/local-assistant-core/actions/runs/45004636677/job/137153462640) | Success; 2860 passed, 1 skipped, 1197 deselected, 1 warning; 81% coverage; Ruff/format, Bandit, pip-audit and policy steps succeeded. |
| containers | [137153462647](https://github.com/LYF-FC/local-assistant-core/actions/runs/45004636677/job/137153462647) | Success; browser phases, TLS/container probes and synthetic Work recovery checks completed; final smoke verification logged. |
| postgres | [137153462506](https://github.com/LYF-FC/local-assistant-core/actions/runs/45004636677/job/137153462506) | Success; 1197 passed, 2861 deselected, 1 warning, no test skips reported; full synthetic backup/isolated restore step passed. |
| ci | [137158072440](https://github.com/LYF-FC/local-assistant-core/actions/runs/45004636677/job/137158072440) | Success; aggregate gate passed for full profile. |

**Skip and audit inspection.** The backend log reports one global test skip and
`test_recovery_set_fsset.py .......s......................`; the only executable
skip in that module is `test_t6_device_node_member_is_rejected`, which skips on
`PermissionError` with “device nodes need privilege”. This is a source/progress-based
attribution, not a named node-ID/reason printed by the hosted run. No named hosted
T6 pass is established. The format and publish module progress has no skip marker;
this is aggregate evidence, not separately named T13/T31 results. Complementary
privilege evidence or the human reviewer's explicit disposition remains necessary.
The one backend warning is Starlette's httpx TestClient deprecation. Pip-audit reports
no known vulnerabilities for audited dependencies but explicitly cannot audit the
local `butler-backend (0.1.0)` package because it is not on PyPI; do not imply an audit
of that local package.

**Browser phase skips.** The initial full listing selected 131 named cases and
reported 61 passed/70 skipped under the optional-phase guards. Dedicated phases
then passed: inbox 4, archive 3, PDF 5, answers/calendar/routines/invoice/email/
installation 36, Work 22, with no further skips reported. A comparison of the
reporter's exact `e2e/file:line:column › title` strings found 70 unique later-phase
cases, all present in the initial 131-case listing, with none absent. Combined
with the source guards and harness phase selection, this supports 131 distinct
browser cases exercised successfully across phases; the initial 70 skip events
remain recorded, rather than being relabelled as initial-phase passes.

**Recovery evidence inspected.** The PostgreSQL log reports: valid recovery set
verified, six negative mutation classes and three different-installation checks
rejected; verifier timing 264 ms, informational synthetic timing only. It also
reports the Spec 075 custom dump restored from exact staged bytes after source
mutation; restored identity/schema mismatches and invalid dump rejected; all
results quarantined, with no activation or forgetting reconciliation claim.
Subsequent original/history/Work/session/credential/suppression checkpoint drill
checks completed successfully. The new staging integration module has 20 success
markers; the full PostgreSQL test summary has no skip. The integration test command
ran for 988.30 seconds (16m28s); the whole PostgreSQL job took 18m57s against its
unchanged 20-minute limit. Its warning is the same Starlette TestClient deprecation.
The successful suite does not explain the older local failures retained in Spec 075
convergence, and those failures remain historical evidence with unresolved causes.

**Selection versus skips.** Backend selected 2861 of 4058 collected cases; 1197
integration cases were deliberately deselected there. PostgreSQL selected those
1197 integration cases and deselected the complementary 2861. Deselection under
these markers is not a skipped CI job or a test pass. The one backend skip and
the browser phase skip events remain separately accounted for above. No named
privileged T6 result or new human criterion-level review was produced by this run.

**Next human handoff.** Use this run for the exact-target V10 coverage assessment,
then perform/record the pending V1–V13 source/criterion/document judgements. Decide
explicitly whether the historical complementary privilege results suffice, or
obtain named results in an appropriately authorized disposable environment. Do
not rerun the entire unchanged suite merely to replace those focused evidence gaps.
Human V1–V13 findings/sign-off, independent verification, C1–C5 closure and owner
acceptance remain pending. No acceptance or reviewer checkbox was changed.

Only this existing handoff file was edited. The owner subsequently authorized a
local commit on the dedicated branch; the base and runtime review target in 7.1
remain unchanged. At the time this handoff was prepared, it had not been pushed or submitted as a PR. It was later published with owner authorization in [PR #72](https://github.com/LYF-FC/local-assistant-core/pull/72); the review target above remains unchanged. Publication does not constitute reviewer sign-off or owner acceptance. Repository
policy, all 23 CI-scope tests, generated-view verification, Markdown/local-link
validation and `git diff --check` were rerun after the evidence update. No runtime,
dependency, workflow, migration, master/register status or generated file changed.
