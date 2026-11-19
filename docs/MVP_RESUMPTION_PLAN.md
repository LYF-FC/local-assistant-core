# MVP resumption and deferred tooling work

Prepared 18 November 2026 under the [owner's scheduling decision](../DECISIONS.md#18-november-2026--defer-experimental-frontend-tooling-replacement-until-the-first-minor-release-after-mvp).
[PROJECT_MASTER.md](../PROJECT_MASTER.md) owns scope, scheduling and status. This
packet prepares the next work; it does not introduce another status register.

## 1. What is deferred

The experimental frontend tooling replacement and temporary picomatch-patch route
are scheduled for the **first minor release after an accepted MVP**. The numeric
version and date are unassigned. Stop expanding these experiments as MVP feature
work. Preserve their evidence for the follow-up; do not present the patch or the
one-file trial as a compatible whole-toolchain replacement.

The later engineering review must cover the unresolved matching regressions,
the other 784 unit tests, browser-tooling source inventory, development HMR and
full build/browser/container evidence. It must retain the ordinary full audit,
negative controls and exact-head CI. No architecture, package pin or replacement
is selected by this scheduling decision.

This is an engineering deferral, not removal of recovery, browser coverage or
security obligations from the MVP. It accepts no gate and authorizes no operation.

## 2. Resume through the unchanged audit and CI gates

Later on 18 November 2026 the owner authorized the needed actions on PRs #54–#56,
including an exception for the blocking audit finding if required. A subsequent
check found [GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf)
withdrawn on 18 November. Two fresh audits on the unchanged main dependency lock
reported exit 0 and zero findings; one used a fresh cache and `--prefer-online`.
The registry remained npmjs.org and picomatch remained 4.0.7.

**No exception is activated.** The original full audit, high threshold, scope
selection and aggregate gate remain unchanged. No suppression, omitted development
dependencies, package relabelling, workflow bypass or `continue-on-error` is added.
Withdrawal does not prove the matching behavior fixed, and earlier failed runs
are not rewritten as passes.

PR #55's incompatible patch is closed without merging. Complete PR #56's
reconciliation, incorporate updated main into PR #54, and inspect fresh required
CI before merging. Runtime implementation can proceed through the normal gates;
no result is inferred from withdrawal alone. This does not accept a gate or
permit deployment, real keys/sets, measurements, NAS access or restoration. See
[the later owner decision](../DECISIONS.md#18-november-2026--owner-authorizes-resuming-implementation-advisory-withdrawal-makes-an-exception-unnecessary).

## 3. Merged review target and historical boundary

The current completion-review target is main
`1c94e445db3dcc74a0133813b35300d205a64380`, the PR #54 merge. The initial packet
was prepared at `05b97c5177cd4bcffc21a3fcd84fd1488f491d9a` (PR #53 merge), before
PR #54 merged; that historical preparation is not current main's normative state.

- PR #54's clarification, 248-case guard file and corrected M5 plan are now merged.
  All six PR-head jobs passed in CI #186 at `df308cd4a8bfda17fa0c573bdba7a17d88386af4`.
  CI #187 is the separate push/main run at the exact target; do not transfer its
  result from #186 or a documentation-only run.
- PR #55's incompatible patch was closed without merging; it is not on main.
- PR #56 merged at `67ca361f4cc96cd29a8c1aa84e8068be39df19c9` to record the owner
  decisions and withdrawal. Its docs-only CI is not runtime evidence.

Use [the exact-revision human-review handoff](SPEC_074_REVIEW_TARGET_1C94E445.md)
and [the owner-decision worksheet](SPEC_074_OWNER_DECISION_WORKSHEET.md) for the
next bounded batch. The reviewer handoff is preparation, not human findings. The worksheet now records
the scoped owner design/planning approvals while leaving detailed choices pending;
neither is a Spec 074 completion declaration.

## 4. Next MVP work: Spec 074 owner/reviewer packet

These recommendations consolidate the existing Phase C drafts for review. The owner approved C1–C3 design baselines, C4 planning only and C5 manual-ceremony
requirements on 18 November 2026. Remaining detailed choices are pending. These
approvals do not tick C1–C5 or authorize a new key, set, measurement or provider access. Personal identities and physical locations belong
in separately authorized private records, not this public packet.

| Item | Approved design/planning baseline | Remaining decision or evidence |
|---|---|---|
| C1 custody | Use the existing encrypted removable-container baseline, separate primary/recovery copies and independent fingerprint/hash-record keeper; operator access is temporary. Both custodians can forge HMACs. | Actual roles/media/locations, presentation/session details and rotation/compromise authority; any degraded exception needs a separate decision. No custody is activated. |
| C2 hash governance | Option A: witnessed initial recording as the baseline. Optional B: later key-holder comparison, labelled honestly. Independently held records are not independent HMAC verification. | Actual recorder/witness/approver assignments and storage/update/dispute details; B is optional, not a separately approved run. No new keyless tool or secret holder. |
| C3 retention | Keep the set/copy inventory; approved manifest co-retirement with its set and authentication records/keys retained while governed manifests require them. Do not restore older non-Work sets without reconciliation. | Every lifetime, early-purge promise, destruction authority, deletion evidence and operational inventory procedure. Key destruction is not data erasure; no deletion occurs. |
| C4 capacity | Prepare the bounded authorization sheet below; use small injected limits for boundary logic rather than near-ceiling sparse files. | Environment, synthetic-key permission, budgets, tiers and stop conditions. No campaign or ceiling is approved; 64 GiB remains a placeholder. |
| C5 generation requirements | Manual-ceremony requirements are approved; no dedicated tooling is commissioned. | Detailed manual procedure/evidence and any later execution authority remain pending. No key generation or management tool is implemented or run. |

Detailed sources: [custody](RECOVERY_KEY_CUSTODY.md),
[hash governance](RECOVERY_HASH_GOVERNANCE.md), [retention](RECOVERY_RETENTION.md),
[capacity](RECOVERY_CAPACITY_VALIDATION.md),
[non-operational implementation](RECOVERY_PHASE_C_IMPLEMENTATION.md).

### Concrete proposals for the next review

The [C4 pilot proposal](RECOVERY_C4_MEASUREMENT_PROPOSAL.md) supplies suggested
numeric limits and a selected small synthetic scope; those limits are **proposals,
not approvals**. The [manual-ceremony procedure](RECOVERY_MANUAL_CEREMONY_PROCEDURE.md)
turns the approved requirements into review steps and execution-readiness gates.
Both were requested as draft preparation on 19 November 2026. No measurement,
synthetic or real key generation, ceremony or merge is authorized by these drafts.
The owner worksheet's run/operational fields remain pending.

### C4 authorization sheet — preparation only

Every field below remains pending; this document supplies no default permission.

| Field | Required before any separately approved run |
|---|---|
| Disposable environment | Named isolated host/filesystem and cleanup owner; no production or NAS path. |
| Data and key permission | Synthetic-only fixtures; explicit approval if a synthetic key is needed. No real key or set. |
| Resource budget | Maximum file size/count, temporary disk, RAM, I/O, elapsed time and available-space floor, chosen before the run. No implied 64 GiB tier. |
| Measurements | Selected M1–M9 procedures, repetitions and instrumentation, with hypotheses separated from criteria. Interruption/disk-full tests need their own bounded scratch environment. |
| Boundary logic | Review the merged PR #54 M5 correction: only above-limit dumps reject from metadata before hashing; otherwise-valid below/equal inputs may hash. Use small injected limits. The older wording remains historical; the correction is now on main. |
| Stop conditions | Exceeding any approved budget, leaving the scratch boundary, unexpected access/write, inability to clean up or encountering non-synthetic inputs. Record failure and stop. |
| Exclusions | No capacity/measurement run is authorized now. Staging/restore and recovery-time evidence require separate authority and the Spec 075 boundary. |
| Output | Exact revision/environment/commands, source hashes, raw observations and limitations; no inferred operational ceiling, RPO or RTO. |

### Human reviewer handoff

Use [appendix section 9](RECOVERY_INDEPENDENT_VERIFICATION_TRACEABILITY.md#9-reviewer-checklist-pending-human-review)
as the existing V1–V13 checklist. Leave every checkbox untouched.
The implementer/assistant must not sign the human reviewer's findings.

Prioritize V3 (A5/overlap text and the now-merged PR #54 guards), V5 (T25 against the recorded
decision), V9 (A13 document review), V10 (exact-revision full coverage), V11
(privilege-dependent cases) and V13 (a new reviewer record for the actual checked
revision). Preserve the other checklist items. Record missing or contradictory
evidence; do not transfer results from a different head or treat a docs-only run
as a runtime pass.

This packet completes preparation only. The reviewer must record their actual
revision, checks and findings. Independent verification, Phase C acceptance and
operational readiness remain separate decisions with their existing prerequisites.

## 5. Following Spec 074: prepare the reserved Spec 075 contract

After the bounded Spec 074 closure/review work, prepare a contract for restore and
staging from exact verified bytes, restored-database installation binding, older
non-Work forgetting reconciliation and a clean-host rehearsal/evidence boundary.
Actual recovery-time/RPO/RTO claims require later measurements and acceptance.

The reservation is in [appendix section 10](RECOVERY_INDEPENDENT_VERIFICATION_TRACEABILITY.md)
and the [Spec 074 task boundary](../specs/074-recovery-set-manifest/tasks.md).
There is no Spec 075 implementation or accepted gate in this packet. A contract is
not permission to restore, access NAS/production, create real keys or adopt private
data. Any implementation batch remains separately scoped and reviewed.

## 6. Review boundaries

This scheduling/packet reconciliation edits no runtime, dependency, workflow, migration,
frozen specification, reviewer record, acceptance contract or generated status
view. The later owner instruction closes PR #55 without merging; no gate/register/task checkbox changes. Existing trials
remain disposable evidence, not an adopted replacement. Only the owner can accept
the relevant MVP scope after its required evidence exists.
