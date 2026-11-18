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

## 2. What still blocks delivery

The picomatch advisory [GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf)
remains unresolved in the reviewed dependency graph. Deferral is not remediation.
The existing `npm audit --audit-level=high`, conservative CI selection and aggregate
gate stay unchanged. No suppressed advisory, omitted development dependencies,
threshold reduction, package relabelling or merge exception is authorized.

Documentation/review and isolated development can proceed. Runtime/test work must
not be disguised as documentation to avoid the required job. A documentation-only
CI pass is not runtime evidence and does not clear the advisory. Required passing
checks remain necessary before the blocked changes can merge or release readiness
can be established. The post-MVP scheduling target does not promise that an MVP
can be released first while this required check remains failed.

## 3. Exact baseline and open-PR boundary

The preparation baseline is main `05b97c5177cd4bcffc21a3fcd84fd1488f491d9a`, the
merge of PR #53. Main contains the Spec 074 criterion index and pending reviewer
checklist. It does not contain the changes in either PR below.

- [PR #54](https://github.com/LYF-FC/local-assistant-core/pull/54), reviewed head
  `e69252b05835607ecf62b48e37179ef29751f843`: owner-approved overlap wording,
  focused guards and corrected C4 M5 planning. Open, draft, unmerged at preparation.
  Its recorded exact-head CI #179 passes scope/backend/postgres/containers, while
  frontend and aggregate CI fail at the audit. No merge or readiness is inferred.
- [PR #55](https://github.com/LYF-FC/local-assistant-core/pull/55): separate temporary
  dependency candidate. Neither the matching failures nor advisory are declared
  resolved. This deferral does not close, merge or mark it ready.

Review main's normative text separately from the proposed corrections in PR #54.
The owner's approval of an interpretation does not make the branch merged or its
implementation independently verified. No new runtime run is claimed here.

## 4. Next MVP work: Spec 074 owner/reviewer packet

These recommendations consolidate the existing Phase C drafts for review. They
are **not approved choices**, do not tick C1–C5, and require no new key, set,
measurement or provider access. Personal identities and physical locations belong
in separately authorized private records, not this public packet.

| Item | Recommendation for review | Explicit decision still needed |
|---|---|---|
| C1 custody | Use the existing encrypted removable-container baseline, separate primary/recovery copies and independent fingerprint/hash-record keeper; operator access is temporary. Both custodians can forge HMACs. | Role separation, medium/process, session controls and rotation/compromise authority; a written degraded arrangement or deferral of real use if distinct roles are unavailable. No custody is activated. |
| C2 hash governance | Option A: witnessed initial recording as the baseline. Optional B: later key-holder comparison, labelled honestly. Independently held records are not independent HMAC verification. | Recorder/witness/approver roles, independent record storage/update/dispute process and whether optional checks are wanted. No new keyless tool or secret holder. |
| C3 retention | Keep the set/copy inventory; propose manifest co-retirement with its set and authentication records/keys retained while governed manifests require them. Do not restore older non-Work sets without reconciliation. | Every lifetime, early-purge promise, destruction authority, deletion evidence and inventory rule. Key destruction is not data erasure; no deletion occurs. |
| C4 capacity | Prepare the bounded authorization sheet below; use small injected limits for boundary logic rather than near-ceiling sparse files. | Environment, synthetic-key permission, budgets, tiers and stop conditions. No campaign or ceiling is approved; 64 GiB remains a placeholder. |
| C5 generation requirements | Decide whether a documented manual ceremony is sufficient before considering dedicated tooling. Existing requirements are a review input. | Manual versus dedicated tooling, and any later implementation authorization. No key generation or management tool is implemented or run. |

Detailed sources: [custody](RECOVERY_KEY_CUSTODY.md),
[hash governance](RECOVERY_HASH_GOVERNANCE.md), [retention](RECOVERY_RETENTION.md),
[capacity](RECOVERY_CAPACITY_VALIDATION.md),
[non-operational implementation](RECOVERY_PHASE_C_IMPLEMENTATION.md).

### C4 authorization sheet — preparation only

Every field below remains pending; this document supplies no default permission.

| Field | Required before any separately approved run |
|---|---|
| Disposable environment | Named isolated host/filesystem and cleanup owner; no production or NAS path. |
| Data and key permission | Synthetic-only fixtures; explicit approval if a synthetic key is needed. No real key or set. |
| Resource budget | Maximum file size/count, temporary disk, RAM, I/O, elapsed time and available-space floor, chosen before the run. No implied 64 GiB tier. |
| Measurements | Selected M1–M9 procedures, repetitions and instrumentation, with hypotheses separated from criteria. Interruption/disk-full tests need their own bounded scratch environment. |
| Boundary logic | Review PR #54's M5 correction: only above-limit dumps reject from metadata before hashing; otherwise-valid below/equal inputs may hash. Use small injected limits. Main's older wording remains separately identified until reconciled. |
| Stop conditions | Exceeding any approved budget, leaving the scratch boundary, unexpected access/write, inability to clean up or encountering non-synthetic inputs. Record failure and stop. |
| Exclusions | No capacity/measurement run is authorized now. Staging/restore and recovery-time evidence require separate authority and the Spec 075 boundary. |
| Output | Exact revision/environment/commands, source hashes, raw observations and limitations; no inferred operational ceiling, RPO or RTO. |

### Human reviewer handoff

Use [appendix section 9](RECOVERY_INDEPENDENT_VERIFICATION_TRACEABILITY.md#9-reviewer-checklist-pending-human-review)
as the existing V1–V13 checklist. Leave every checkbox untouched.
The implementer/assistant must not sign the human reviewer's findings.

Prioritize V3 (A5/overlap text versus main and PR #54), V5 (T25 against the recorded
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

This scheduling/packet change edits no runtime, dependency, workflow, migration,
frozen specification, reviewer record, acceptance contract or generated status
view. It closes no PR and changes no gate/register/task checkbox. Existing trials
remain disposable evidence, not an adopted replacement. Only the owner can accept
the relevant MVP scope after its required evidence exists.
