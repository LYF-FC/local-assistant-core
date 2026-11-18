# Spec 074 — human reviewer handoff at merged revision 1c94e445

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
