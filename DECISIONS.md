# Decisions

> Decision log: design and scope decisions. Explicit owner-approved decisions recorded here rank above [PROJECT_MASTER.md](PROJECT_MASTER.md) until reflected in it, and must be reflected in it. Delivery status of what was decided is owned by the master, not recorded here. Historical decisions are not rewritten.

Local structured authority, explicit current permissions, transactional minimal audit, restricted roles and deterministic workflows are foundational. Production and external integrations remain gated. Small document BYTEA staging is temporary; durable archive remains separate. See [architecture](ARCHITECTURE.md), [security](SECURITY.md) and [CI](docs/CI_COMPUTE.md).

## Scope and delivery reconciliation

The complete generic [register](docs/FEATURE_REGISTER.md), [MVP acceptance](docs/MVP_ACCEPTANCE.md) and [explicit reconciliation](docs/SCOPE_RECONCILIATION.md) supersede abbreviated source-snapshot planning as an exhaustive scope description. Short views must retain parent mappings and may not remove long-term requirements. Overlaps remain explicit; private configuration and historical evidence stay outside Git.

Development proceeds in substantial dependency-aware batches after owner review/merge of the planning PR. Finish local verification before one completed batch push where practical; required CI failures and review fixes justify additional runs. There is no commit cap or fixed PR countdown. No auto-merge. Synthetic engineering, merged delivery, host/provider acceptance and release certification are distinct.

FastAPI/PostgreSQL/React, Windmill/Home Assistant and separate NOMAD boundaries remain. Local storage/test adapters can unblock development without real NAS/provider access. Calendar writes, alternate orchestrators/frameworks, external AI, production and private namespace conversion remain separately reviewed choices, not incidental authority from this scope.

## Local archive transition — spec 050

Keep original bytes in PostgreSQL while introducing explicitly provisioned local disk copies. A pre-copy committed immutable root binding makes cleanup obligations durable; status re-verifies bytes rather than persisting a stale success flag. This deliberately separates storage failure/recovery acceptance from PDF/OCR parser changes. It does not replace Synology as the intended durable archive layer or activate a live share. No configuration change can silently discharge a bound document's managed-copy cleanup obligation.

## PDF derivation — spec 051

Extend the existing document lifecycle rather than create a second ingestion store. Preserve exact originals on extraction failure, expose bounded failure states, and require explicit owner review before citation. A separate local worker confines native parsing; upload idempotency is owner-scoped and payload-bound. Re-extraction creates an unreviewed version with build provenance. OCR and structured field extraction remain separate dependencies; this supersedes no original storage or deletion contract.

## Explicit bounded OCR — spec 052

OCR is an explicit owner derivation, never an automatic fallback or accuracy assertion. Preserve the exact source and previous derivations; expose uncertainty and require fresh review before citations. Keep the existing text mode as default and use an additive validator migration. Structured fields/uncertainty and filing remain separate retained outcomes.

## Reusable household installations — approved 8 November 2026

Retain the original 135 requirements and add INSTALL-01–12, bringing the register to 147. Develop one shared core with independent private installations, configurable members, safe templates, optional feature lifecycle and tested upgrades. Stable software keys are distinct from local identities. Enabling a feature grants no content permission; disabling is not deletion. Finish this milestone before legacy private-data adoption or a reusable-installation release; independent document work can proceed. [Detailed contract](docs/CONFIGURABLE_INSTALLATIONS.md). No runtime/schema change, account provisioning, deployment or migration is authorized by this documentation update.

## Task/model specialization investigation — approved 8 November 2026

Add RND-04/05 to the prior 147 requirements (149 total), retaining all existing scope. Compare one general local model with task specialists, and dense with sparse MoE, using current primary sources and reproducible task/hardware measurements. No architecture is preferred in advance; keep negative findings and adopt/defer/reject rationale. Multi-model routing implementation, weight downloads/experiments and production promotion remain separate steps. [Contract](docs/LLM_RESEARCH.md).

## Scoped source answers — spec 053

Begin local document answering with exact source quotations rather than unvalidated generated assertions. Model-disabled source search remains useful offline. Keep the local selector behind a default-disabled explicit model/digest configuration, current grants, two-phase audit and strict citation validation. This chooses an adapter protocol, not model weights, dense/MoE architecture, task-routing strategy or production activation. Free-form synthesis/conversation and real FR/ES/EN quality remain retained requirements.

## Calendar and briefing — spec 054

Implement the normalized complete-window boundary and deterministic briefing before activating calendar accounts. Full snapshots are bounded and all-or-nothing; omissions only imply removal in overlapping coverage. Preserve recurrence identity and original zone, reject contradictory sequence/cursor/fetch data and retain last good content on offline/failure. Do not infer cross-calendar duplicates or choose between overlaps. Live provider semantics, writes/mirroring and installation onboarding remain separate.

## Recurring routines — spec 055

Begin recurrence with explicit finite plans, earlier-fold/skip-gap rules and latest-only bounded downtime catch-up. Correct/resume affects future creation; stable routine/local-date identities cannot replay a materialized date. Pause/correction cancels linked active reminders; aggregate forgetting scrubs generated task copies/history. Use existing in-app reminder policies and keep external send/activation separate. No monthly/exception/calendar or production claim follows.

## Invoice field review — spec 056

Extend source review with deterministic bounded candidates and explicitly attested confirmed/unknown fields before mailbox/filing work. Human review is not model confidence or payment authority. Duplicate hints preserve conflicting originals and never approve deletion/filing; DOC-04 cleanup remains distinct. Derived-only forgetting is terminal and retains the original; aggregate document forgetting scrubs derived copies in the same transaction. See [contract](docs/INVOICE_REVIEW.md).

## Reviewed invoice filing plans — spec 057

Deliver reviewed logical naming/destination proposals before an apply adapter. Reuse source-bound invoice history and forgetting; avoid duplicate original/approval stores. A plan approval cannot become a ticket for future autonomous execution. Unknown fields need explicit manual paths; destination inventory/authorization/collision/containment and exactly-once effects remain separate. [Limits](docs/INVOICE_FILING_PLANS.md).

## Offline email intake — spec 058

Preserve original email before live mailbox integration using a strict offline single-attachment boundary. Raw email can contain incidental private context, so shared document access does not grant envelope access. Exact raw-message replay is distinct from semantic forwarded-copy/business dedup. Terminal forgetting retains only a disclosed private message-checksum tombstone; scrub raw content, initial filename and attachment checksum. Do not treat sender headers or plan approval as authority. [Rationale/limits](docs/OFFLINE_EMAIL_INTAKE.md).

## Feature overview and scope review — spec 059

Publish individually reviewed requirements without deleting/merging canonical IDs or approving candidate additions. Distinguish engineering slices, accepted MVP user journeys and full retained feature contracts. A shared primitive can satisfy multiple requirements while permissions and acceptance remain separate. Existing milestone labels stay; v1.2 remains unallocated. This decision records review/measurement discipline, not acceptance of every recommendation or new runtime architecture. [Method and recommendations](docs/FEATURE_REVIEW.md).


### Spec060 (merged PR #15): explicit installation initialization and reviewed templates

[Contract](docs/INSTALLATION_SETUP.md): migration/read do not mint installation identity; first confirmed initialization does. Defaults are bounded setup state, not global rewrites of existing timezone/language records. Shareable allowlisted templates carry only languages/timezone; independent initialization creates fresh identity, private recovery preserves identity. Readiness is an informational dependency catalogue with no activation controls or health claims. Existing trusted provisioning remains required; onboarding, dynamic grants, lifecycle compaction and feature controls remain open.


### 9 November 2026 — approve the deferred review programme

Owner approved all individual/whole-product review recommendations, generalization/consolidation/validation/challenge work, the shared implementation map and former candidates A–F. [Contract](docs/DEFERRED_REVIEW_PROGRAMME.md). Schedule after the entire pre-review 149-reference implementation scope and later stages; this supersedes earlier pending-approval labels and proposed priority shifts, without delaying existing safety duties or earlier MVP acceptance. Preserve all baseline outcomes/IDs and original 99 counts; add REV-01–06 as planned supporting bundles with parent mapping, not six independent product features. Existing behavior can satisfy an improvement without needless rewriting. No production/provider/private-data authorization is conferred. Spec060 merged PR15 provides partial installation foundations, not complete installation acceptance.


### Spec062 (merged PR #17) — compose baseline attention without another queue

Use [an explicit daily overview](docs/DAILY_OVERVIEW.md) over existing scoped APIs, retaining separate owner/domain authority and honest first-page/freshness limits. Keep sign-in landing behavior and require manual refresh; do not add ambient all-scope queries, a global approval claim or a new mutation surface. Destination context is in memory and server-reread, never an authority token. Full review/refactoring directions remain deferred; existing MVP usability/privacy obligations continue now.


### Spec063 design — financial input is not a forecast or action authority

[The capture contract](docs/FINANCIAL_CAPTURE.md) separates owner-recorded confirmed inputs, assumptions, forecasts and unknowns; accepted plans require payload-bound record-only acknowledgement and reset on material correction. Store typed financial records with server validation, not arbitrary Memory profiles labelled as finance. Existing finance scope remains owner-private with explicit current grants. This is a future implementation boundary, not permission to calculate, connect providers, transfer funds or adopt private data.


### Spec064 (merged PR #19) — deliver the finance server boundary independently

Implement [typed storage/API](docs/FINANCIAL_REGISTER_API.md) and its PostgreSQL/recovery evidence before the financial UI. Unknown versus zero/forecast, current owner/grant and record-only plan acknowledgement are server-enforced. Corrections reset acceptance; generic approvals/Memory do not confer financial authority. This is a bounded foundation, not reduced FIN-06 scope. UI/freshness/whole-MVP and later finance remain required.


### Spec065 (merged PR #20) — finish the financial owner workflow

Use [explicit typed forms and separate acknowledgements](docs/FINANCIAL_UI.md) for plan-record acceptance, private-copy export and managed forgetting. Unknown amounts stay null; zero and forecasts keep explicit labels. Kind/owner/scope cannot change through correction, and accepted plans grant no execution authority. Reuse reviewed APIs; no backend/schema changes or new finance calculation. Dashboard promotes only verified merged PR19 server evidence, preserving the original 99 cohort and later/deferred scope.


### Spec066 (merged PR #21) — observations must retain uncertainty

Use [explicit observed/configured/disabled/unknown states](docs/OPERATIONS_OVERVIEW.md), not a global green health badge. Installed versions do not establish approval/support/license/advisory status. Preserve INSERT-only runtime audit access: audit review stays unavailable until a narrow separately reviewed projection exists; OPS-10 is retained. Sample only current actor technical-admin jobs, without payloads/global counts/overdue inference.


### Spec067 (merged PR #22) — bounded search before complete unified inbox

Prove delivery semantics against a [synthetic channel](docs/NOTIFICATIONS.md) before any real connector: commit the attempt claim before sending, treat timeouts as unknown and reconcile by lookup instead of resending, and keep one delivery per reminder cycle. Real providers need a separate spike and authorization.

Execute approved invoice plans only through a [separate, exact, single-use owner request](docs/FILING_EXECUTION.md) that is consumed atomically by the first claim and bound to one owner, scope and plan revision; plan approval stays non-executable. Define destination identity by an explicit canonical-path policy and treat its hash as a uniqueness handle, not a security boundary. Describe the guarantee as single claimant plus reconcile-before-retry, conditional on a destination that honours a key and answers lookup; never as unconditional exactly-once. Forgetting is a first-class operation that scrubs keys and history snapshots idempotently while keeping history append-only.

Use [one explicit scope and two existing libraries](docs/SCOPED_RECORD_SEARCH.md), with honest page/unavailable/review labels. Do not call first pages complete global search or generate rankings/advice. Keep pending approvals, Memory/finance/Work and semantic search requirements open. Current-source rereads and minimal navigation targets prevent old matches becoming edit authority.


### 10 November 2026 — synthetic MVP first, real connectors by spike, real data last

Complete the everyday MVP against synthetic data/adapters before real services. Validate high-risk adapters (calendar and notification first, then mail intake and local model) through short time-boxed spikes using throwaway accounts and synthetic content, ideally before further features depend on their sealed schemas. Use real private data only last, under separate authorization. Rationale: keeps private data out of development and keeps activation gated while reducing late surprises from provider behaviour. A spike confers no production authority and each account/data flow needs explicit approval. See the [roadmap strategy](ROADMAP.md#delivery-strategy--synthetic-mvp-first-then-connector-spikes-agreed-10-november-2026).

### 14 November 2026 — Spec073 design: overdue and stalled work observation (owner decisions D1–D4)

The owner approved four decisions for the frozen [overdue and stalled work observation](specs/073-overdue-stalled-work/spec.md) design. **D1:** technical administrators may see household-wide state derived from members' private reminder, notification, filing and approved-job records, as queue-level states only (no counts, ages, owners, scopes, records, ids or per-item details); the residual risk that repeated reloads can reveal approximately when, and in small households possibly whose, item became due is accepted, and audit records but does not prevent such probing. **D2:** a fixed 120-second grace period applies to the observer only; workers are never delayed, and the measurement assumes a non-decreasing application clock. **D3:** migration 0038 classifies `operations.work_status` as `operations_read`, keeping the seven-category audit summary shape. **D4:** queues whose workers are not deployed in the default Compose stack may show overdue, and the view must state that it is not a worker-health check. These decisions approve the documented design only: they do not authorize implementation, expand scope, or change any requirement, priority, acceptance criterion or gate status.

### 15 November 2026 — Spec074 (recovery-set manifest): Phase B acceptance, two acknowledged interpretations, Phase C design-only authorization

The owner decisions that fixed the [frozen specification](specs/074-recovery-set-manifest/spec.md) (O1a to O9 and the related decisions of its section 10.1; frozen on 14 November 2026) are recorded there and are not restated here. This entry records later owner decisions that the frozen specification cannot carry.

**Phase B acceptance (15 November 2026).** The owner formally accepted the synthetic-only Phase B implementation of spec 074, merged in [PR #40](https://github.com/LYF-FC/local-assistant-core/pull/40) (merge `47b949e`). The acceptance is bounded to that synthetic-only scope: it is not acceptance of Gate 11, MVP-05 or any other gate, it is not independent verification and it is not a recovery-readiness or RPO/RTO claim. The independent-verification record at an exact `main` revision remains outstanding.

**Two implementation interpretations, explicitly acknowledged and accepted by the owner (15 November 2026).**
1. The section 3.4 / section 7.3 discrepancy: the implementation preserves the closed section 7.3 output schema and reports only the first violation; it adds no count field and no repeated reason codes.
2. The stale-temporary-link interpretation: if temporary-link removal fails after publication but the directory fsync confirms durability, the result is `published_durable` with `stale_temporary_present`; the resulting set remains unverifiable until the temporary link is removed.

The frozen specification is not edited; [docs/RECOVERY_SET.md](docs/RECOVERY_SET.md) documents both.

**Phase C design-only authorization (15 November 2026).** The owner authorized design and preparatory work only for Phase C (key custody, expected-hash governance, retention and forgetting, capacity, key-generation requirements). This does not authorize Phase C implementation, key-management or key-generation tooling, generating, provisioning, storing or rotating a real key, creating or operating a real recovery set, operational recovery or restore, connecting to the NAS or any production storage, running measurements or synthetic-key test runs, or any migration, schema or configuration change. Proposals and designs are not decisions: each deferred matter (O1b, O2 retention, O5 governance, O8 dump ceiling, O9) stays deferred until the owner decides it. This entry changes no requirement, priority, acceptance criterion or gate status; Gates 6, 10 and 11, OPS-09, OPS-10 and MVP-05 are unchanged. The authorized Phase C design/preparation package was delivered as documentation-only PR #42 (merge `b081c12`): five reviewable draft documents and a blank independent-verification template. Their merge records delivery of drafts only; it does not approve any proposal, complete C1–C5 implementation/measurement tasks, satisfy independent verification, or authorize implementation or operations.

### 15 November 2026 — Spec074 Phase C: implementation of the non-operational portions authorized

On 15 November 2026, after the Phase C design drafts merged ([PR #42](https://github.com/LYF-FC/local-assistant-core/pull/42)), the owner explicitly authorized implementation across the five Phase C workstreams (C1 key custody, C2 expected-hash governance, C3 retention and forgetting, C4 capacity validation, C5 key-generation requirements) as one coordinated batch. It extends the design-only authorization recorded in the entry above (same date) for the non-operational portions only. The authorization excludes, and the owner retained as prohibited: generating, provisioning, storing, rotating or activating a real recovery key; creating or operating a real recovery set; real recovery or restore; NAS or production-storage access; capacity measurements and large-data runs; synthetic-key test runs for governance or capacity; key-generation or key-management tooling; migrations, schema or configuration changes outside the approved plan; claims of operational readiness or independent verification; promotion of Gate 6, Gate 10, Gate 11, OPS-09, OPS-10 or MVP-05; and merging any pull request. Proposals and designs remain proposals and each open owner decision (O1b, O2 retention periods, O5, O8 and the dump ceiling, O9) stays open until the owner decides it; independent verification remains a separate prerequisite. The implemented scope is described in [docs/RECOVERY_PHASE_C_IMPLEMENTATION.md](docs/RECOVERY_PHASE_C_IMPLEMENTATION.md). It was delivered and merged in [PR #43](https://github.com/LYF-FC/local-assistant-core/pull/43), merge commit `708e8134098846a40e0c49cae5a954913aef9fdb`, on 15 November 2026. Merge records delivery only: it is not independent verification, owner acceptance of Phase C, completion of C1–C5, or operational authorization. This entry changes no requirement, priority, acceptance criterion or gate status.

### 16 November 2026 — Spec074: T25 second-scenario expected code reconciled with the written verification order

On 16 November 2026 (Europe/Paris) the owner explicitly decided, by their own instruction, to retain the existing verification order of the [frozen specification](specs/074-recovery-set-manifest/spec.md): the key's installation binding is checked **before** the key references and the MAC verification. For T25's second scenario (installation A's key and fingerprint presented with installation B's manifest) the expected rejection is **`key_installation_mismatch`**, with the states of the section 2.5 row "Key bound to a different installation than the manifest declares" (authenticity invalid; integrity, expectations and freshness not evaluated; exit 1).

The precedence was already specified: section 2.5 (its combinations row), section 6.2 (which states this code for exactly this shape) and section 7.2 step 3 all place the binding check first, as does T17. T25's expected column, which listed `manifest_authentication_failed` or `manifest_key_reference_mismatch` for the second scenario, was inconsistent with them. The conflict was found while mapping the tests to the criteria and recorded as unresolved in the [traceability appendix](docs/RECOVERY_INDEPENDENT_VERIFICATION_TRACEABILITY.md) and in [PR #51](https://github.com/LYF-FC/local-assistant-core/pull/51); the owner then decided it as stated here.

Effect: the second-scenario expected code in the spec's T25 row is corrected to `key_installation_mismatch` (the first and third scenarios and every other row are unchanged) and the correction is recorded in the spec as a separately labelled post-freeze clarification. The original freeze (14 November 2026, the content of commit `f903237a69e6e2eeeef8b057abef3fc618a27630`) is not rewritten or re-dated and this is not a new freeze; the current text is that revision plus this one correction. **Implementation behavior is unchanged:** the verification order is retained, nothing in the runtime changes, and the existing test `test_t25_cross_installation_substitution` (merged in PR #51 as `28a2d79`) already asserts this exact outcome.

This decision does not authorize runtime changes, acceptance of any criterion or gate, operational activity, or the closure of any other requirement. Independent verification of spec 074 and the Phase C owner decisions (C1 to C5) remain open, and no register, gate or acceptance status changes.

### 17 November 2026 — Spec074: bounded metadata-only exception for the stage-1 overlap pre-check

On 17 November 2026 (Europe/Paris) the owner explicitly approved this bounded exception: after every required argument is present and every argument shape is validated, the tool may perform filesystem metadata checks solely to detect overlapping paths and aliases before reading file contents.

**Resolves** the specification-conformance finding recorded in the [traceability appendix](docs/RECOVERY_INDEPENDENT_VERIFICATION_TRACEABILITY.md) and [PR #53](https://github.com/LYF-FC/local-assistant-core/pull/53): the [frozen specification](specs/074-recovery-set-manifest/spec.md) section 2.5 described stage 1 as "no file access" and listed `paths_overlap` among the stage-1 codes, while the implementation's overlap check makes metadata calls (16 `os.lstat` measured for a manifest inside `SET`). The finding was open and no interpretation had been adopted; this decision adopts the exception below and no other.

**The permitted operations, from the implementation (`backend/app/recovery_set/cli.py`, `_spellings`, `_same_existing_file`, `_overlaps`):** the lexical normalization of each supplied path (no file access); symlink resolution by `os.path.realpath` (`lstat` and `readlink` of path components); and a same-file comparison of the key and the manifest or output path (`os.stat` and `os.path.samestat`). An overlap rejection remains `paths_overlap`, exit 2, with all four states `*_not_evaluated`.

**Preserved, unchanged:** zero filesystem access when rejecting a missing or malformed argument shape or a parser error, including when the supplied paths would overlap; no content read, directory-content enumeration, write or publication during overlap checking; the symlink-resolved and same-file overlap protections; the no-follow protected opens, single-link checks, rejection behavior and the documented race limitation (the pre-check names paths as they are at that moment). The exception is not a general exception for stage-1 file access and not a statement that metadata access is never file access. The lexical-only alternative that had been proposed is **not** adopted, and no runtime change was made.

**Effect:** the specification carries a separately labelled post-freeze clarification (sections 2.5, A5 and the overlap sentence of section 7.1; the head-of-document note). The original freeze (14 November 2026, `f903237a69e6e2eeeef8b057abef3fc618a27630`) and the 16 November 2026 T25 correction are not rewritten or re-dated; this is not a new freeze, and the current text is that revision plus the two recorded clarifications. Focused tests were added to hold the implementation to the exception.

This decision approves the wording only. It is not independent verification and not acceptance of A5, T36 or any criterion or gate, and it authorizes no operational activity, key or recovery-set use, capacity measurement, restoration or NAS/production access. Independent verification of spec 074 and the Phase C owner decisions (C1 to C5) remain open, and no register, gate or acceptance status changes.


### 18 November 2026 — Defer experimental frontend tooling replacement until the first minor release after MVP

The owner directed: set this work aside from the MVP, record it clearly, fix it in
the next minor version after MVP, and resume the MVP. This decision schedules the
experimental frontend tooling replacement and its temporary picomatch-patch route
for the **first minor release after an accepted MVP**. No numeric release version
or date is assigned. It does not remove a user-facing feature from the eleven MVP
gates, defer Spec 074's recovery requirements, or approve the incomplete patch.

The deferred engineering work includes completing or replacing the PR #55 temporary
patch, migrating Vite/Vitest to an alternative toolchain, the remaining unit-test
migration, development HMR parity and browser-tooling remediation. The one-file
esbuild/Node trial is bounded feasibility evidence only; it is not an adopted
architecture or whole-suite replacement. PR #54's Spec 074 clarification and tests
remain separate recovery work, not part of this deferral. Neither PR is closed,
merged, marked ready or accepted by this decision.

The security finding is not resolved or waived. The existing full audit, CI scope
selection and aggregate gate remain mandatory and unchanged. Deferring the
migration does not turn failed CI into a pass or authorize an MVP release with a
failed required check. A separate reviewed resolution is still needed before
blocked runtime changes can merge or MVP readiness can be established; no release
exception is granted here. Do not split runtime/test changes into documentation
PRs to avoid the failing job, relabel a package, omit development dependencies,
lower the audit threshold or suppress the advisory.

The immediate work focus resumes **Spec 074's existing MVP scope**, beginning with
its owner-decision/reviewer packet and pending independent document review. Spec
075 restore-contract planning follows that bounded closure work; no restore
implementation or operation is authorized here. The full longer-term proposed
priority order is not approved by this narrower instruction.

[PROJECT_MASTER.md](PROJECT_MASTER.md) reflects this scheduling decision. The
[resumption packet](docs/MVP_RESUMPTION_PLAN.md) records the post-MVP follow-up and
the next non-operational MVP work. No frozen specification, acceptance procedure,
gate/register/task checkbox, verification result or operational authorization
changes. C1–C5 remain open; real keys, sets, measurements, NAS access and restoration
remain separately gated.


### 18 November 2026 — Owner authorizes resuming implementation; advisory withdrawal makes an exception unnecessary

After the deferral entry above, the owner explicitly changed the earlier
instruction and authorized bypassing the blocking audit finding as needed to
resume implementation, including the needed actions on PRs #54, #55 and #56.
This later instruction supersedes the earlier prohibition on a narrowly reviewed
exception for that finding; it does not accept a gate or authorize operations.

Before activating an exception, a fresh check found that GitHub had marked
[GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf) **withdrawn
on 18 November 2026**. Two actual full `npm audit --audit-level=high --json` runs
on the unchanged main lock reported **exit 0 and zero findings**, including one
with a fresh cache and `--prefer-online` against `https://registry.npmjs.org/`.
Picomatch remains 4.0.7; no dependency was relabelled or updated. Withdrawal and a
zero-finding report are not evidence that the observed matching behavior was fixed.

Therefore **no audit exception is activated**: keep the original full audit,
threshold, workflow selection and aggregate gate unchanged. The authorized but
unneeded exception prototype is not part of the delivery. This approval is not
a standing blanket waiver for unrelated or future findings; those retain their
ordinary review and required-check boundaries.

The owner authorizes closing the incompatible PR #55 **without merging** its
patch, completing and merging PR #56's documentation reconciliation after its
checks, and refreshing PR #54 against updated main and merging it only after
fresh required CI passes. No unattended auto-merge is enabled. The tooling
migration remains deferred to the first minor release after MVP; the original
release numbering remains unassigned.

The earlier failed CI remains attributed to its original run. Fresh passing
results must be read on the actual refreshed head; no result is inferred from
withdrawal alone. Implementation can resume through the normal gates when those
checks pass. No frozen specification change is included here, and no independent
verification, MVP/Phase C acceptance, capacity measurement, real-key/set use,
NAS/production access, restoration or private-data adoption is authorized.


### 18 November 2026 — Spec074: C1–C3 design, C4 planning and C5 manual-ceremony requirements approved

The owner explicitly approved the C1–C3 design recommendations, C4 planning only
and C5 manual-ceremony requirements, and instructed recording the decisions and
merging PR #57 while keeping acceptance and operational statuses unchanged.
The approval refers to the worksheet and recommendation summary prepared from
main `1c94e445db3dcc74a0133813b35300d205a64380`; this entry is the authoritative
record of that bounded approval, not a human-verification or operational record.

- **C1 design approved:** encrypted removable-container baseline on a supported
  POSIX filesystem; physically separate primary/recovery copies; separate
  custodians and independent fingerprint/hash-record keeper; temporary operator
  access. Both symmetric-key holders can forge HMACs: separation is procedural.
  Actual people/media/locations/hosts, presentation and residue controls, session
  details, intervals and compromise/rotation procedures remain unassigned or
  unresolved. No degraded arrangement is implicitly approved and no custody is
  activated.
- **C2 design approved:** option A witnessed initial recording as the baseline;
  option B may be an optional later comparison by an existing key holder. That
  later comparison is not independent HMAC verification. Independently held,
  append-only/superseded records remain distinct from keys/sets/verifier hosts.
  No new keyless tool or additional holder is selected. Detailed assignments,
  storage/update/dispute rules and any option E process remain unresolved.
- **C3 design relationships approved:** copy inventory; co-retirement of a
  manifest and its set; expected-hash records retained while governed manifests
  remain; fingerprints/old keys retained while needed for authentication; deletion
  evidence referencing sets rather than forgotten object identifiers. Every actual
  lifetime, expiry trigger, early-purge promise, destruction authority and evidence
  method remains unresolved. Key destruction is not erasure. Older non-Work sets
  are not safe to restore merely because they verify; reconciliation remains open.
- **C4 planning only approved:** the bounded future-authorization sheet may be
  used to prepare explicit resource budgets, environment, synthetic-fixture/key
  permissions, procedures and stop conditions. No campaign, synthetic-key run,
  large-data test, interruption/disk-full experiment or measurement is authorized.
  Numeric budgets and the real operational ceiling remain undecided; 64 GiB is
  unapproved. Small injected-limit M5 logic is not capacity evidence. No staging
  or restore measurement is authorized.
- **C5 manual-ceremony requirements approved:** use the documented manual route
  and the existing KG-1–KG-11 requirements as the requirements baseline; no
  dedicated key-generation tool is commissioned. Detailed procedure and evidence
  remain to be prepared/reviewed. This approves requirements, not execution of a
  ceremony, key generation, provisioning or key-management operations.

The [worksheet](docs/SPEC_074_OWNER_DECISION_WORKSHEET.md) and master distinguish
these approved design/planning choices from the remaining fields. C1–C5 remain
unchecked. Independent human review, Phase C/Spec 074/MVP acceptance, real-key/set
use, custody activation, capacity/ceiling evidence, NAS/production access,
restoration and private-data adoption remain unchanged and separately gated.
No frozen specification, manifest format, runtime, dependency, migration or CI
policy changes. PR #57 may merge after its updated documentation checks; no
unattended automerge is enabled. Spec 075 implementation is not authorized here.


### 19 November 2026 — Prepare C4 measurement and manual-ceremony drafts only

The owner authorized agents to prepare a concrete C4 measurement proposal and a
manual-ceremony procedure in a draft PR. The instruction explicitly excludes
running measurements, generating keys, changing acceptance or operational
statuses, and merging. This is preparation authority only; the 18 November
C1–C3 design, C4 planning-only and C5 manual-requirements approval remains the
baseline. No proposed numeric budget, execution method, environment, campaign or
ceremony is approved by publication or review of these drafts. Outstanding human
verification, C1–C5 task states and all operational restrictions remain unchanged.

### 19 November 2026 — Spec075 first synthetic staging and restored binding slice authorized

The owner subsequently authorized the first bounded Spec 075 contract and implementation, disposable PostgreSQL validation and preparation of a draft PR. The [first-slice contract](specs/075-synthetic-recovery-staging/spec.md) limits work to synthetic dump-only private staging/verification, immutable verified-byte handoff into an isolated restore target, and fail-closed binding of actual restored installation singleton/Alembic head to explicit trusted expectations. Internal helpers and the existing guarded engineering drill may be extended; no general operational restore CLI is authorized.

Normal synthetic test keys and synthetic fixtures are authorized only as necessary for this engineering slice and its disposable tests. This is distinct from the real/manual key ceremony, which remains unauthorized. There is no C4 measurement/capacity campaign, real key/set, private-data adoption, NAS/production access, operational recovery, release/deployment or automatic merge permission. No new migration, schema or application permission change is included.

Non-Work older-backup forgetting reconciliation is not implemented by this slice. Every result remains quarantined and ineligible for release/use; a structurally bound synthetic restore is not complete recovery or permission to use an older backup. Archive installation, credential/configuration/model recovery, clean-host independence and RPO/RTO remain later scoped work. Spec 074 Phase C tasks and independent verification remain open. This advances a separately authorized engineering slice without declaring Spec 074 or the whole of Spec 075 complete, changing any gate/status/acceptance or waiving normal quality/CI review. Integration and evidence belong in [PROJECT_MASTER.md](PROJECT_MASTER.md) and the [convergence record](specs/075-synthetic-recovery-staging/convergence.md), not an inferred outcome of this decision.


### 20 November 2026 — Run isolated picomatch research in parallel without blocking MVP delivery

The owner agreed to leave the current picomatch dependency and matching behavior unchanged for the MVP, while commissioning a separate, research-only Claude workstream to investigate a safe and compatible resolution. In parallel, the MVP critical path continues through the existing Spec 074 independent-verification work. This formalizes two independent workstreams; it does not reopen PR #55 or revise the 18 November post-MVP tooling deferral.

**MVP critical path.** Continue the existing Spec 074 review using the already-prepared exact-revision human-review handoff. Refresh all evidence against the actual current `main` revision, identify which historical observations remain applicable and which must be rerun, and obtain appropriate exact-head full-coverage CI evidence. Keep AI-assisted source/test inspection distinct from the human reviewer's own findings and sign-off. Do not create a duplicate reviewer handoff. Do not begin a new implementation batch or promote a gate/status merely because evidence has been refreshed; first resolve the existing review and then reassess the next MVP scope from reconciled `main`.

**Picomatch research stream.** Research must run in an isolated branch, worktree, sandbox or equivalent environment separate from active MVP work. It is non-blocking and research-only: no changes to `main`, active MVP branches, production, package manifests/lockfiles, dependency versions, audit thresholds, CI workflows, required checks or MVP schedule. No PR, cherry-pick, merge, deployment, dependency update, waiver or implementation is authorized. A candidate or recommendation is a report, not permission to implement it. If no candidate meets the acceptance criteria, report that no viable solution was found rather than forcing a patch.

A credible candidate must demonstrate compatibility with the repository's existing valid matching behavior (including the regressions exposed by PR #55), adversarial ReDoS resistance, bounded performance under representative and adversarial inputs, and maintainability/provenance including upstream support or a sustainable patch strategy. The research report must include reproducible source revisions, exact patches/prototypes confined to the isolated environment, baseline and candidate test corpus/results, adversarial cases and timeouts, performance methodology/results, dependency provenance, limitations and a recommendation. A candidate is not acceptable based only on passing a narrow reproduction or on an advisory status change.

If research uncovers credible evidence of a material security vulnerability affecting the currently deployed application, notify the owner immediately with evidence and scope. Otherwise, findings remain on the deferred, non-blocking track. Research cadence and persistence depend on the capabilities of the configured Claude environment; no indefinite background execution is implied by this decision. If persistent or scheduled execution is unavailable, report that limitation and operate only in explicitly initiated research sessions.

The [picomatch research protocol](docs/PICOMATCH_RESEARCH_PROTOCOL.md) and [MVP resumption packet](docs/MVP_RESUMPTION_PLAN.md) define the operating boundaries. This decision changes no dependency, runtime, frozen specification, acceptance criterion, gate/register/task checkbox, CI policy or operational authorization. It does not resolve the matching issue, approve a patch, or alter the first-minor-release-after-accepted-MVP deferral.

### 22 November 2026 — Approve the MVP-01 synthetic invoice journey and Mac-local rehearsal

The owner approved one bounded journey and local rehearsal scope: a synthetic adult signs in privately on desktop/mobile, reviews an agenda, imports the exact same provided invoice `.eml` twice without duplication, reviews the source, asks an authorized cited question, schedules an in-app reminder, reviews invoice fields and a logical filing plan, separately authorizes the exact plan for a **synthetic metadata destination**, sees execution status/history and resumes after a controlled application/worker restart with preserved records and no duplicate effect. After the independent A5 validation contract was finalized, the owner authorized implementation by the Lead Engineer on the dedicated branch `work/mvp01-invoice/a3-implementation`.

Scope boundary: synthetic data only on the owner's Mac and local Docker; an opt-in durable synthetic filing collaborator for the rehearsal worker (a marked metadata ledger on a Docker named volume — filing identity, logical path, SHA-256 and size, never invoice bytes and never a real filesystem or NAS result); browser request/status/history controls over the existing exact-revision filing API; an owner-runnable rehearsal interface. Architecture is chosen proportionately with stated limits; no sidecar service is approved. Excluded: live providers, private records, a real destination, payments, outbound AI, operational recovery, capacity/key ceremonies, a generic approvals redesign, semantic search, deployment and production access. No security protection, role grant, trigger, rate limit or clock is changed.

The owner's authorizations on 22 November 2026 were separate and sequential: first the implementation and local synthetic checks; then, after the independent A5 contract, the local implementation commits (no push); then, separately, the owner authorized pushing the branch and opening one pull request against `main` (authorization only; this entry, as originally written, asserted no push or pull request had occurred; see the dated merge record below). Merging, auto-merge, force-pushes, CI exceptions, release, acceptance of any gate beyond the accepted scope below, host trust changes and real-world activation remain the owner's and are not authorized by any of this, and none of it is evidence of any other approval. The historical Spec 074/075 decisions and the pending Spec 074 review are preserved and not displaced.

**Acceptance (22 November 2026).** The owner personally ran the journey on their Mac and accepted the *MVP-01 synthetic invoice journey*: environment = local Docker Compose project `local-assistant-core-mvp01-owner`, commit `17628594e037397ad013333b5e6dc785757aa8c7`, synthetic data only; scope = the [spec 076](specs/076-mvp01-synthetic-invoice-journey/spec.md) journey with a **simulated** filing destination (metadata ledger), a **simulated** answer model and a **simulated** calendar; restart evidence = container restart and SIGKILL of the application and workers only. Not covered: a host reboot, a real destination or NAS, a real model or provider, clean-host recovery, MVP-03/Gate 7 real-destination evidence, Gate 11, the whole MVP and every other gate; none is promoted. **Re-confirmation (22 November 2026):** the owner re-confirmed the acceptance for commit `193ccb865eaa63cb85b408b734778ad2629fa920` (the head of pull request #77 at that time) after trying, on their Mac stack rebuilt from that commit, the filing-plan suggestion, the reminder preferences and the filing panel after sign-in. The other journey steps were tried by the owner on `17628594e037397ad013333b5e6dc785757aa8c7` and that acceptance for them stands. The environment, the simulated parts, the restart evidence and the not-covered list are unchanged. Any commit after `193ccb8` (the record commit that contains this text) changes documentation or printed text only and is not separately accepted. CI evidence lives in the pull request metadata, not in this repository. Implementation, integration, testing, verification and acceptance remain separate facts (see [PROJECT_MASTER.md](PROJECT_MASTER.md)). See the [contract](specs/076-mvp01-synthetic-invoice-journey/spec.md) and the [owner rehearsal guide](docs/MVP01_OWNER_REHEARSAL.md).

**Merge record (22 November 2026; factual, no new decision).** Following the owner's push-and-pull-request authorization above, pull request #77 was opened and merged by the owner on 22 November 2026 at merge commit `2a5a0cde92f3f4cfdaf12b53f442948989c267b2` (head `e631be90cbc65de4c586ac5a55614008b6dc60c0`). The text above is preserved as the record at the time it was written: statements there that no push or pull request existed, or that #77 was open, are superseded by this line. The merge changes the *integration* fact only; the acceptance scope and its not-covered list are unchanged and no gate is promoted.

### 22 November 2026 — Approve the next MVP-01 journey ("The bad-connection day") in its recommended form and allow a new batch before the Spec 074 review is resolved

After the owner accepted the synthetic invoice journey (spec 076) and merged it, the Journey Architect recommended one next journey and the owner approved it in its recommended form with these answers (the owner confirmed them to A1 on 22 November 2026):

- **Journey and scope.** One synthetic household adult has a normal day on phone and Mac while the simulated answer model is stopped, the synthetic calendar source is offline and the synthetic filing destination is unreachable, and a second synthetic invoice arrives anyway. The day stays usable (agenda with honest staleness and no free-day claim; reminders still fire without a model; an explicit "assistant unavailable"); the invoice's filing request visibly waits with a plain reason and is neither lost nor shown as failed; the waiting state survives a SIGKILL restart; when the outage ends the invoice is filed exactly once with no duplicate; and the second synthetic adult never sees the first adult's records. It reuses the accepted spec 076 stack (single named project `local-assistant-core-mvp01-owner`) and is a second, separate journey, not a change to the accepted one.
- **Smallest slice.** A second synthetic invoice fixture; one owner-runnable outage on/off composed from existing controls; owner-readable reason text and honest wording for a waiting/unknown filing, an unavailable assistant and a stale calendar; clear behaviour when the answer service is actually stopped; a live peer-side negative check; a rehearsal guide section. **No migration, no new service, no new filing state and no change to spec 069 semantics** (reason text only).
- **Excluded.** Destination capacity exhaustion; real Wi-Fi/DNS fault injection by tooling (turning the Mac's Wi-Fi off is an optional action only the owner performs); the optional technical-administrator ("admin hat") steps and any new grant; host reboot; clean-host recovery; real calendar, notification, model or mailbox providers; NAS; payments; outbound AI; semantic search; a generic approvals redesign; multi-stack concurrency; scheduled alerting. Everything stays simulated and nothing leaves the installation.
- **The 20 November constraint.** A new implementation batch may start before the Spec 074 independent review is resolved. This answers the 20 November decision ("Do not begin a new implementation batch … first resolve the existing review") **for this batch only**: the Spec 074 review remains pending and is not displaced, and no Spec 074/075 operational restriction, gate or status changes.
- **Acceptance.** The owner will decide acceptance personally after trying the journey, naming the environment and scope; the acceptance wording is not pre-approved here.

This authorizes specification, validation design, implementation and local synthetic checks by the Lead Engineer on a dedicated branch (committing, pushing, opening or merging a pull request, and accepting any gate remain separately owner-authorized) and does not authorize a live provider, private data, a real destination, outbound AI, a model choice (none is recorded in this repository) or any security-control change. Implementation, integration, testing, verification and acceptance are separate facts and none exists yet for this journey; see [PROJECT_MASTER.md](PROJECT_MASTER.md).

**Acceptance (23 November 2026; recorded as a fact after the owner's trial, no new decision).** The owner followed the agent-prepared 10-step trial script on their own Mac and accepted the *spec 077 "bad-connection day" journey*: environment = local Docker Compose project `local-assistant-core-mvp01-owner` (database `butler_test_mvp01_owner`, `https://localhost:18444/`), installed revision `2cd4ecec8c4d3221c5a9b0ccbecedd8e59622648` (the head of pull request #84 at that time), synthetic data only; scope = the [spec 077](specs/077-mvp01-bad-connection-day/spec.md) journey over a **simulated** outage, a **simulated** answer model and calendar and a **simulated** filing destination; restart evidence = SIGKILL of the application and workers only. Observed: the briefing with the offline calendar stayed honest, the assistant was reported as unavailable, the reminder was delivered once, the second invoice was imported twice and its filing waited as Unknown, two SIGKILL restarts produced no second effect, and after the outage was ended the invoice was filed once after about 15 minutes (ledger effects 1 to 2) with the replay and answer checks matching. Not covered: a real network failure, a real model, calendar or provider, a host reboot, clean-host recovery, a NAS, MVP-03/Gate 7 real-destination evidence, Gate 8/MVP-04, MVP-01 as a whole and every other gate; none is promoted. It does not extend the spec 076 acceptance, says nothing about Spec 074, a model choice or real integrations, and any commit after `2cd4ece` is not separately accepted. Pull request #84 was subsequently merged by the owner on 23 November 2026 at merge commit `7d56324e133aa150d0bb9da1f5f56963a7c013c9`; the acceptance above was given at the PR head `2cd4ece` before the merge and is not an acceptance of the merge commit. Implementation, integration, testing, verification and acceptance remain separate facts (see [PROJECT_MASTER.md](PROJECT_MASTER.md) and the [convergence record](specs/077-mvp01-bad-connection-day/convergence.md)).

### 22 November 2026 — Consider the Spec 074 independent-review workstream done; no Hermes/model decision

The owner decided, in their words to A1, "Let's consider Spec074 done." This closes the Spec 074 independent-review workstream as an open item for **planning purposes**: the 20 November 2026 decision made that review the MVP critical path and said not to begin a new implementation batch until it was resolved (the owner had already allowed one batch to start before it was resolved, in the entry above). That constraint is now moot.

What this decision is not: it is the owner's decision, **not independent human verification evidence** — no new reviewer sign-off exists in the repository and none is claimed. It does not accept Gate 11 or MVP-05, does not change any recorded implementation, integration, testing, verification or acceptance status of Spec 074 or Spec 075, and does not lift any operational restriction (real keys/sets, custody, capacity, NAS/production access, restoration, private-data adoption). Evidence that is missing stays recorded as missing in [PROJECT_MASTER.md](PROJECT_MASTER.md). If the owner meant something broader or narrower, this record is to be corrected by a later owner decision.

The owner also set aside any model choice for now ("Forget about Hermes for now, we'll research the best model when the time will come"): no model is selected, no model research is commissioned by this entry and the existing [model research contract](docs/LLM_RESEARCH.md) is unchanged. The master's "proposed — awaiting owner confirmation" priority list remains unconfirmed; only the owner can confirm it.
