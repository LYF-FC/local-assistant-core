# Spec 074 owner decision worksheet — design review and future measurement proposal

Prepared 18 November 2026 against main `1c94e445db3dcc74a0133813b35300d205a64380` (PR #54 merge). **Every decision field below is PENDING.** This is a docs-only review worksheet, not an approval record or another status authority. [PROJECT_MASTER.md](../PROJECT_MASTER.md) owns current scope and status; [Spec 074 tasks](../specs/074-recovery-set-manifest/tasks.md) retain the C1–C5 task definitions and unchecked boxes.

The next owner decision can approve or modify the **design baselines** for C1–C3 and the C5 requirements direction while keeping actual operations unauthorized. The C4 section prepares a separate, bounded measurement-authorization decision; it authorizes no run. Design approval does not supply measurements, activate custody, complete C1–C5, establish independent verification, accept Phase C or Spec 074, or accept the MVP.

Completing the whole of Spec 074 cannot be claimed under the current absence of operational and measurement authority: its outstanding tasks require evidence and outcomes beyond this packet. This worksheet is the next bounded step only. Any later Spec 075 contract preparation follows an agreed closure/sequencing boundary; it does not make Spec 074 complete automatically.

## 1. How to record a bounded decision

For each design item, the owner can choose **approve the stated design baseline**, **modify (state changes)**, or **defer**. No choice is preselected. Record the precise scope, remaining conditions and decision reference; reflect any actual owner-approved decision in the authoritative project record through a separately reviewed change. This worksheet alone does not change that record.

| Decision metadata | Value |
|---|---|
| Owner decision reference and date | PENDING |
| Revision and sections reviewed | PENDING |
| C1 design disposition and amendments | PENDING |
| C2 design disposition and amendments | PENDING |
| C3 design disposition and amendments | PENDING |
| C5 requirements direction and amendments | PENDING |
| C4 future-run authorization disposition | PENDING — no run authorized |
| Conditions, unresolved questions and next review | PENDING |

Public review records should contain role descriptions and opaque references only. Actual people, host identities, medium identifiers, physical locations, private inventories and access details belong in separately authorized private records. **Approving a role or storage design is distinct from assigning people, selecting actual media/hosts or activating custody.** Do not put keys, fingerprints, real hashes/sets, credentials or private operational details in this worksheet or Git.

## 2. C1 — custody design recommendation

Recommendation from [RECOVERY_KEY_CUSTODY.md](RECOVERY_KEY_CUSTODY.md), sections 2–7: use the existing encrypted removable-container baseline with a supported POSIX filesystem, physically separate primary and recovery copies, an independent fingerprint/hash-record keeper and temporary operator access during a separately authorized session. Keep the passphrase apart from its medium. The keeper is distinct from both custodians, and the custodians are distinct; if those roles cannot be separated, require a written owner decision on a degraded arrangement or defer real use.

Both custodians hold the same symmetric HMAC secret and can forge valid manifests. The second copy improves availability only; it provides no authenticity protection against a compromised holder. Separation is procedural, not cryptographic. A generation or verification host handling the secret is a trust boundary; a key-holder-run check is not independent HMAC verification.

| Pending design field | Owner response needed |
|---|---|
| Storage option | PENDING — accept baseline, amend or select an existing alternative with its tradeoffs |
| Role separation/degraded arrangement rule | PENDING — acceptable separation and how any exception is explicitly approved |
| Key presentation and residue (K1) | PENDING — how a mounted supported filesystem presents the protected file; acceptable host/swap residue risk and cleanup evidence |
| Session-host requirement | PENDING — whether a minimal dedicated host is required; no actual host selected here |
| Access, release and return controls | PENDING — session authorization, log responsibility, review interval and aborted-session handling |
| Rotation/loss/compromise procedure | PENDING — cadence, declaration authority, stop-use and known-good re-attestation controls |
| Recovery-path evidence | PENDING — tabletop requirements and separate permission for any later live rehearsal |

Later private fields remain unassigned: accountable custodian, recovery custodian, operator, keeper, media and location inventory, session host and access procedure. No key is generated, copied, stored, released, rotated or activated. Approval of this design would settle only the explicitly approved policy choices; C1 still needs the applicable owner decisions, custody activation and operational-procedure evidence required by its task.

## 3. C2 — expected-hash governance recommendation

Recommendation from [RECOVERY_HASH_GOVERNANCE.md](RECOVERY_HASH_GOVERNANCE.md), sections 2–4: **Option A**, initial witnessed recording/comparison, as the baseline. Keep append-only expected-hash and fingerprint records independently of the set, manifest directory, key storage and verifier host. Record supersession rather than overwriting history. **Option B** may be an optional later check by an existing key holder; no extra holder is proposed. Option E adds value only after its out-of-band approval process is defined and trusted. Options C (another key holder) and D (new keyless tooling) are not recommended in this bounded step.

Witnessing initial recording proves transcription against observed output, not authenticity of that output or a later manifest. A later comparison with the retained hash is a separate act: current `verify` tooling requires the HMAC key. It is a key-holder check, not independent HMAC verification. A retained record alone cannot detect later substitution without that comparison, and a stale supplied hash can match an older manifest. Format-valid approval references do not authenticate an approver or establish authority.

| Pending design field | Owner response needed |
|---|---|
| Options A/B/E | PENDING — accept A, whether B is wanted, and defer E until its process is defined or specify that process |
| Recorder/witness/approver roles | PENDING — role separation and authority rules; no private identities here |
| Independent storage and updates | PENDING — medium class, append/update/supersession procedure and verification of independence |
| Later comparison | PENDING — when it is required and how the existing holder's result is reviewed |
| Lost record, dispute and stale reference | PENDING — stop/use rules, dispute authority, and whether freshness may be relied on before a second reviewer exists |

Approval would settle only those governance design choices. It would not create/retain a real record, prove the record independent or current, authorize a synthetic-key demonstration, add a tool, or close C2's operational governance requirement.

## 4. C3 — retention and forgetting recommendation

Recommendation from [RECOVERY_RETENTION.md](RECOVERY_RETENTION.md), sections 1–4: maintain a copy inventory; co-retire a manifest with its set; retain expected hashes while their manifests are governed, and fingerprints/old keys while retained manifests require authentication. Use deletion evidence referencing sets rather than forgotten object identifiers. Keep report-only reconciliation separate from deletion. These are proposed relationships, not approved lifetimes or a deletion promise.

| Artifact or policy | Pending owner field |
|---|---|
| Recovery sets, including every dump/archive copy | PENDING — lifetime, expiry trigger, copy-inventory rule and accountable destruction role |
| Manifests | PENDING — lifetime and whether proposed co-retirement is adopted |
| Expected-hash records | PENDING — lifetime and retirement rule |
| Fingerprint records/revocation register | PENDING — lifetime compatible with retained manifests |
| Keys, all copies | PENDING — lifetime and retirement/destruction conditions compatible with retained manifests |
| Key-event/generation records | PENDING — lifetime and evidence responsibilities |
| Captured tool output | PENDING — lifetime and handling rule |
| Temporary artifacts | PENDING — review the existing remove-on-discovery procedure and cleanup evidence; no cleanup performed here |
| Early purge on forgetting | PENDING — whether any promise is made, authority, scope and handling of unavailable copies |
| Deletion evidence | PENDING — approved method/authority references, copy-inventory checks and evidence standard |
| Older non-Work sets | PENDING — explicit interim restriction pending separately designed DOC-X02 reconciliation |

No numeric duration is proposed as approved. Application audit retention remains outside this matrix. Destroying an authentication key does not erase the dump/archive data. A verifying manifest never grants permission to restore forgotten material; retention choices do not solve DOC-X02. Older non-Work sets remain blocked from being treated as safe to restore merely because they verify.

Approval would settle the stated policy choices only. It would not prove inventory completeness or deletion, implement DOC-X02, authorize purging/restoring, change live retention or complete C3's remaining requirements.

## 5. C4 — future bounded measurement authorization sheet

Source: [RECOVERY_CAPACITY_VALIDATION.md](RECOVERY_CAPACITY_VALIDATION.md). **PENDING; no capacity campaign, synthetic-key use or large-data run is authorized.** The model in [RECOVERY_PHASE_C_IMPLEMENTATION.md](RECOVERY_PHASE_C_IMPLEMENTATION.md) is unmeasured and unvalidated. The 64 GiB ceiling remains an unapproved placeholder. Existing 1/4/16 GiB tiers and repetitions in the draft are proposals, not a budget or permission.

Before a future run, the owner must approve a concrete sheet with actual numbers and a named disposable scope. Do not interpret a missing value, model input, engineering bound or draft tier as a default authorization. Keep host/path/person details in a private record and use its opaque reference here.

| Required authorization field | Value / constraint |
|---|---|
| Exact code revision, approved procedures and run window | PENDING — identify exact SHA, selected M1–M9 procedures and start/end window |
| Disposable environment and scratch boundary | PENDING — private environment reference, filesystem, isolated scratch boundary, operator and cleanup owner; no real-data/key host, production or NAS |
| Synthetic fixtures and key permission | PENDING — explicit permission for synthetic key creation/use and the approved helper/procedure, fixture provenance and disposal; no real keys or real sets |
| Maximum individual file size and total fixture bytes | PENDING — explicit numeric byte limits, distinguishing logical size from physical allocation |
| Maximum archive entries and total files | PENDING — numeric limits, with each requested M6 case identified |
| Temporary disk budget and available-space floor | PENDING — numeric bytes for peak scratch use and the floor checked before/during each run |
| RAM/swap and I/O budget | PENDING — numeric peak-memory cap, swap policy, total read/write bytes and any throughput cap |
| Elapsed time and repetitions | PENDING — numeric per-run/campaign duration caps and repetition count for each tier |
| Tier and cache plan | PENDING — numeric non-sparse tiers, cold/warm/unknown cache handling and host-load observations; a beyond-RAM tier needs explicit budget or a recorded omission |
| Instrumentation, hypotheses and criteria | PENDING — approved sampling method/interval, observations to retain and criteria distinct from hypotheses; no extrapolated ceiling |
| M7 interruption / M8 disk-full | PENDING — separately bounded scratch environment, numeric disk/time budget and cleanup plan; no host-wide disk fill or uncontrolled interruption |
| M9 filesystem cases | PENDING — exact disposable filesystems/mounts; no network/NAS mounts |
| Evidence and reviewer | PENDING — opaque storage references, exact commands/revision/environment, raw observations, spread, anomalies, exit/reason codes, reviewer role and cleanup evidence |
| Stop authority and numeric trigger values | PENDING — responsible role and thresholds mapped to every resource cap/floor above |

The future sheet must require stopping on any cap/floor breach, leaving the approved scratch boundary, unexpected access/write, encountering non-synthetic material, instrumentation failure or inability to clean up. Record the failure and remaining artifacts; do not expand budgets or resume without a new bounded decision. Approve numeric triggers before execution, not after observing a result.

**Boundary logic is separate from capacity.** Main now contains PR #54's M5 correction: use small injected limits with fixtures at limit minus one, equal and plus one. Only above-limit dumps reject from metadata before hashing; otherwise-valid below/equal dumps may hash. Near-ceiling sparse files can cause large logical reads and are unsuitable as a shortcut. M5 checks establish boundary logic only and supply no measured operational capacity. This worksheet runs neither boundary checks nor measurements.

M1–M9 results, if separately authorized and obtained, would apply only to their measured disposable environment. Page-cache effects, shared-runner noise and sparse allocation limit inference; do not extrapolate from small tiers to 64 GiB. Every result remains informational, not RPO/RTO or recovery-readiness evidence.

C4 requires **measured resource evidence and a separate owner decision on the real operational dump ceiling**. Neither approval of this plan nor approval to measure closes C4. The draft's wider ceiling evidence also needs restore-size ratio, restore working space, real-host disk/growth inputs and a chosen margin; those remain unknown. M10 staging/restore measurement is excluded from this bounded proposal and reserved for separate authority in the later restore/staging specification. A limited M1–M9 campaign cannot silently stand in for the missing envelope evidence.

## 6. C5 — manual ceremony versus dedicated tooling

Recommendation from [RECOVERY_KEY_CUSTODY.md](RECOVERY_KEY_CUSTODY.md), sections 9–10: decide whether a documented manual ceremony is sufficient before commissioning dedicated tooling. The choice is **PENDING**; either route must meet the reviewed requirements and custody decisions. Choosing the manual route does not waive randomness, protected creation, durability, secret-handling or audit controls.

| Pending requirements field | Owner response needed |
|---|---|
| Requirements route | PENDING — documented manual ceremony, dedicated tooling proposal, or defer; explain required repeatability/review needs |
| KG-1–KG-11 review | PENDING — accept/amend the draft requirements: OS cryptographic randomness/fail-closed handling; exact key format and explicit installation binding; separate fingerprint recording; exclusive protected durable output; no secret output/logging; metadata-only records and lifecycle/session controls |
| Dependencies and evidence | PENDING — resolve C1 first; identify review/negative-test expectations and evidence a manual procedure or future tool would need |
| Any later implementation/execution | PENDING — requires a separate explicit scope and authorization; no tooling or ceremony is authorized by selecting a direction |

The existing `FutureKeyOperations` protocol is an interface only. No generation/provisioning workflow is implemented by this worksheet. C5 remains requirements preparation; no key is generated and no key-management tooling is commissioned or run.

## 7. Review outcome and next boundary

The immediate reviewable choice is to approve, modify or defer C1–C3 design baselines and C5 requirements direction, with all unresolved fields stated explicitly. The owner may keep **all actual operations unauthorized** while doing so. If future C4 measurements are wanted, first complete and separately approve the bounded sheet above. No operational permission can be inferred from silence, a design choice, a validator's acceptance reference or this artifact's existence.

Independent verification remains a separate human-review workstream with its actual reviewed revision and evidence. This worksheet does not sign or alter the reviewer record/checklist and does not establish independent verification. It does not tick C1–C5, accept Phase C/Spec 074/MVP, or change any gate/register/status. Restoration and staging belong to reserved Spec 075; this worksheet neither begins its implementation nor authorizes a restore, real-key/set use, NAS/production access, deployment, capacity test or migration/configuration change.

Sources and sequencing: [Spec 074](../specs/074-recovery-set-manifest/spec.md), [tasks](../specs/074-recovery-set-manifest/tasks.md), [Phase C implementation boundaries](RECOVERY_PHASE_C_IMPLEMENTATION.md), and [MVP resumption plan](MVP_RESUMPTION_PLAN.md). The recommendations above consolidate existing drafts; they create no new approved policy or completion shortcut.
