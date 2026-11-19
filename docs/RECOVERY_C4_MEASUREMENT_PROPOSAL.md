# C4 proposal — first small synthetic observation pilot

**Planning proposal only, 19 November 2026. No run is authorized or performed.**
The owner approved preparation of this document, not measurements, synthetic-key
creation/use, fixture creation or a capacity campaign. Every number below is a
**suggested future authorization cap**, calculated on paper, not an observation,
approved operational ceiling or acceptance criterion. Missing private environment,
operator, reviewer or authorization fields mean **stop before any execution**.

Source baseline: main `00234cbec6bd76ab5ff8dcf128776c130c195c27`, including the
18 November C1–C3 design, C4 planning-only and C5 manual-ceremony requirements
decision. See [the decision log](../DECISIONS.md),
[capacity plan](RECOVERY_CAPACITY_VALIDATION.md),
[owner worksheet](SPEC_074_OWNER_DECISION_WORKSHEET.md) and
[non-operational implementation](RECOVERY_PHASE_C_IMPLEMENTATION.md).
This document changes none of those authorizations, no runtime or test source,
no limit, no task checkbox and no acceptance or operational status.

## 1. Question and scope

If separately authorized later, observe only the small-fixture behavior of the
unchanged `generate` and `verify` paths: logical hash throughput (M1), process peak
RSS (M2), external wall time (M3) and sampled publication disk use (M4). The pilot
can expose gross instrumentation or scaling problems within **1–64 MiB**; it
cannot validate large-dump behavior or establish a safe operating limit.

Select three **dump-only**, synthetic, non-sparse tiers with archive expectation
`absent`. The bytes are deliberately not a real PostgreSQL dump; there is no
database access, restore, archive stress or source-data export. The future fixture
producer and its non-sensitive seed reference need review; this proposal supplies
no generator, harness, shell procedure or key command.

| Tier | Dump bytes | Paired repetitions | Recovery commands |
|---|---:|---:|---:|
| Small | 1,048,576 (1 MiB) | 3 | 3 generate + 3 verify |
| Middle | 16,777,216 (16 MiB) | 3 | 3 generate + 3 verify |
| Largest in this pilot | 67,108,864 (64 MiB) | 3 | 3 generate + 3 verify |
| Total | 84,934,656 (81 MiB), fixtures created once | 9 pairs | **18**, no automatic retries or unreported warm-up runs |

Use one fresh, distinct output path for each generation and verify its corresponding
manifest; never overwrite an earlier result. Retain all three observations per
tier, including failures and outliers. A rejected/incomplete run is not replaced
without a new decision about the remaining budget. No separate zero-byte or
missing-dump timing is treated as a valid-set baseline.

All tiers and their combined 81 MiB input fit within the proposed memory envelope.
Creation and any fixture check can warm the cache before the first command. Label
that first cache state **unknown**, with later runs warm/unknown as observed; do
not call any run cold. Do not drop host caches, add a beyond-RAM tier, use sparse
allocation or extrapolate to the draft 1/4/16 GiB tiers or 64 GiB placeholder.

## 2. Proposed environment and aggregate caps

These values are conservative starting constraints, not evidence that the pilot
will fit. A future approver may reject or amend them **before** execution. The
operator must demonstrate the enforcement/accounting mechanism beforehand; if a
cap cannot be enforced or observed, the run does not start.

| Resource or boundary | Suggested maximum / stop threshold |
|---|---|
| Environment | One new, dedicated disposable Linux VM; local virtual disks with one pre-provisioned supported ext4 scratch filesystem separate from the VM root/system filesystem. Only scratch is exercised as the target filesystem; provisioning/mounting are outside the campaign and need their own authority. No production/NAS/network mount, real-data host or real-key host. Actual private profile reference remains pending. |
| Whole VM | **1 vCPU, at most 1 GiB RAM, guest swap disabled, at most 8 GiB virtual disk** including the preinstalled OS/tools and scratch allocation. No other workload. Host/hypervisor cache/storage characteristics must be disclosed privately; they are not measured by guest counters. |
| Campaign process group | At most **512 MiB**, including descendants and charged page cache; observer budget at most **64 MiB** inside the same VM. Per-process peak RSS and group memory are different observations. |
| Scratch boundary | One owner-only directory on a preallocated **512 MiB** scratch filesystem. Peak live use at most **256 MiB**; stop at **224 MiB** used or below **288 MiB** free to leave cleanup/headroom. No allocation outside this directory except preapproved read-only source/tools and bounded VM system activity. |
| VM disk free space | At least **2 GiB** free before starting, after tools/source are provisioned; stop before free space drops below **1 GiB**. This is a pilot guard, not a restore safety margin. |
| Logical application-data reads | At most **1 GiB cumulative userspace read bytes** for all campaign processes/descendants, including fixture checking, dump hashing, manifest reads, cached module/import reads and collector reads. Preflight each next operation against the remaining budget; do not equate payload arithmetic with total process I/O. |
| Logical application-data writes | At most **256 MiB cumulative userspace write bytes** for all campaign processes/descendants, including synthetic inputs, manifests, evidence, captured streams and the ancillary allowance. No rewrite/regeneration of the 81 MiB input set. |
| All campaign guest block I/O | At most **2 GiB read / 512 MiB written**, including startup/filesystem overhead charged to the campaign; proposed maximum rates **8 MiB/s read / 4 MiB/s write**. Stop at **1.75 GiB read / 448 MiB written**, retaining margin for stopping/cleanup. Guest block bytes are not host physical-media bytes. |
| Files | At most **3 dump files, 9 final manifest files, 1 ephemeral synthetic key file and 32 evidence/metadata files**; at most **46 live regular-file names**, including a temporary publication link (an extra name, not a second content inode). One recovery command at a time; a stale temporary stops the pilot. No archive files. |
| Captured evidence | At most **32 MiB** total; at most **64 KiB combined stdout/stderr per recovery command**. Store no key material; record private paths/host descriptions through opaque references. Stop rather than truncate a required result and call it complete. |
| Wall time | At most **900 seconds** from preflight start to completed cleanup. Stop starting active work by **780 seconds**, reserving **120 seconds** for controlled stopping/cleanup. Each recovery command at most **30 seconds**; no automatic retry. |
| Observation cadence | Proposed **100 ms** resource sampling plus kernel/process high-water accounting. A missing sample, unavailable counter, uncontrolled child or collector failure stops the run. Sampled disk peaks must be labelled as sampled, not proven instantaneous maxima. |

The future controller must check remaining worst-case bytes/time before starting
each operation, not rely solely on sampled alarms. Rate limits apply to guest
block I/O; they do not bound the speed of cached logical reads. Those logical
bytes need complete process/descendant accounting, including startup and exited children. If whole-process accounting or enforcement is unavailable, fail preflight; never substitute the paper estimate. The approval sheet must identify
how counter scope, stopping latency and the reserved margins are enforced. These
caps do not prove a bound on the physical I/O of a hypervisor or storage device.

### Planning arithmetic, not measurements

- Inputs: `1 + 16 + 64 = 81 MiB`, written once. One optional full fixture-content
  check adds at most **81 MiB** logical reads; it is budgeted and reported as
  preparation, never included in command throughput.
- At the inspected source, each successful command hashes the dump once:
  `3 repetitions × (generate + verify) × 81 = 486 MiB` dump reads. Generation's
  second set scan checks metadata; it is not another complete dump-content pass.
- Nine manifests at the existing maximum 4 MiB each reserve **36 MiB** for both
  manifest writes and their subsequent verification reads. This is an upper-bound
  allowance, not a predicted manifest size. Publication's temporary hard link and
  final name refer to one inode; do not budget a second manifest-content copy.
- Planned logical content reads are therefore at most `81 + 486 + 36 = 603 MiB`,
  plus at most **1 MiB** for key/ancillary content. The remaining **420 MiB**
  below the 1 GiB cap is headroom for actual module/import, collector and protocol
  reads, not a claim about their size. Observe/account for all of them; stop if
  they do not fit. Extra content checks consume budget and are not implicit.
- Peak planned scratch allowance is `81 inputs + 36 manifests + 32 evidence +
  2 ancillary/metadata = 151 MiB`. It fits below the **224 MiB stop threshold**
  and **256 MiB maximum**, with the separate 512 MiB filesystem/free-space rule.
  The 2 MiB is application ancillary/metadata allowance, not a measured ext4
  metadata/journal/reservation size. Actual filesystem overhead and available-space
  accounting remain subject to the separate stop thresholds; no fit is guaranteed.
  Planned logical writes have the same conservative **151 MiB** allowance, below
  256 MiB; guest filesystem/journal effects are observed under the separate block cap.
- Maximum regular-file allowance: `3 + 9 + 1 + 32 = 45`; one temporary publication
  artifact makes **46**. A leftover is a stop condition, not permission to accumulate more.
- Suggested phase limits: preflight **45 s**, fixture creation/checking **90 s**,
  recovery commands **18 × 30 = 540 s**, summary **60 s**, cleanup **60 s**:
  **795 s** total. Active phases use at most **735 s**, below the 780 s active cutoff.
  There is no promise that these limits will suffice; exhaustion means stop/inconclusive.

## 3. Future procedure and observations — not an execution authorization

1. After a separate owner decision, verify the approved exact source, private
   environment scope, installed tools, all enforcement controls, initial resource
   headroom and cleanup responsibility. No install/download or VM/filesystem
   provisioning is part of the measurement window; provision only under its own
   approved preparation scope and include its storage in the 8 GiB limit.
2. Create only the approved three non-sparse synthetic files. Check logical size,
   regular-file/link/mode constraints and allocated-block information. A virtual
   disk may still compress/deduplicate content below the guest: non-sparse guest
   allocation alone proves no physical-media throughput. Stop if fixture provenance
   or allocation is unknown or the current unmodified tool cannot accept the fixture.
3. Use at most one ephemeral **synthetic** recovery key outside SET and manifest
   output directories. Its creation/use/disposal, and any use of the existing
   test helper outside the test suite, require explicit separate permission. This
   proposal creates no key and does not commission a generator or supersede the
   manual-ceremony requirements. No real key, set, production identifier or archive.
4. For each tier, execute the three ordered generate/verify pairs only if the next
   pair fits the remaining worst-case budgets. Keep trust inputs explicit. A hash
   copied from this synthetic generation output is a fixture input, not independent
   proof of freshness, installation provenance or recovery completeness.
5. M1: record dump bytes divided by externally observed operation wall time as
   **end-to-end logical bytes/s**, including startup and other command overhead;
   do not mislabel it isolated hashing or storage throughput. M2: use the proposed
   Linux child-process kernel maximum RSS (convert KiB to bytes), and record its
   scope separately from group/cache high-water figures. M3: external monotonic
   time, the tool's informational elapsed time, all three values and median/range;
   state timer precision/rounding. M4: record before/during/after free space and
   file allocation, including sampling limitations and publication-link semantics.
6. Any unexpected exit/reason, malformed/missing output, unexpected access/write,
   cap/floor or time breach, stale temporary, non-synthetic input, loss of isolation
   or cleanup doubt stops the campaign. Record the failure and remaining artifacts.
   Emergency stopping is a resource safeguard, not an M7 fault-injection experiment.
   No retry, expanded budget or improvised cleanup outside the approved boundary.
7. Retain observations privately through opaque references, reconcile the synthetic
   file/key inventory and record approved cleanup. If stopping prevents cleanup,
   preserve the disposable environment isolated for the named cleanup owner; do
   not run host-wide cleanup or declare disposal complete without evidence.

No performance pass/fail threshold is proposed. Whether observations support a
small-fixture hypothesis is reported as supported/not supported/inconclusive.
The three short tiers cannot establish linearity, constant memory at arbitrary
sizes, cold-I/O behavior, operational capacity or a 64 GiB ceiling.

## 4. M5 boundary logic — separate future test authorization

M5 is not part of the 18-command timing pilot. A separately approved, small
test-runner check may propose a **4,096-byte injected dump limit** and synthetic
fixtures of **4,095 / 4,096 / 4,097 bytes**. Inspect both generate and verify:
only the last rejects with `set_size_limit_exceeded` from metadata before dump
hashing; otherwise-valid below/equal fixtures must reach hashing, subject to all
other validation. Count actual hash calls and output/publication outcomes; do not
infer the below/equal behavior from an above-limit-only test.

The supported injection is a **test-only Python function parameter**:
`Limits(dump_bytes=...)` supplied to `generate(..., limits=...)` or
`verify(..., limits=...)`. There is no public limit CLI flag, environment variable
or configuration setting. Do not add one or use a near-64-GiB sparse fixture.
Existing `test_t35_limits_are_enforced_before_hashing` and
`test_limit_injection_is_unreachable_from_cli_environment_or_configuration`
are inspection inputs; this document does not claim they already supply the
complete six-way boundary matrix.

Suggested separate M5 envelope: **1 runner process, 60 s, 512 MiB group memory,
64 MiB scratch, 64 MiB total process logical reads, 48 MiB total process logical writes**, with no retry. Retain the same proposed VM/CPU/no-swap boundary; allow at most **128 MiB guest block reads / 96 MiB guest block writes**, subject to the same complete-accounting preflight and no host physical-I/O inference.
Reserve at most **3 × 4 MiB** setup manifests and **6 × 4 MiB** result manifests,
**8 MiB** evidence and **1 MiB** fixtures/ancillary space: **45 MiB**, below
48 MiB writes and 64 MiB scratch. At most three setup generations plus the six
boundary calls, fixtures totalling **12,288 bytes** (not MiB), and no archive.
Below/equal verify setup must be described without changing test assertions or
relying on an invalid manifest; the exact future harness and synthetic-key
permissions remain for review. There is no harness added or run in this PR.

M5 findings would be boundary-logic evidence only. The M5 authorization and its
envelope are separate decisions; unused timing-pilot budget is not permission
to perform these tests. Their results cannot be combined with pilot timings as
capacity observations.

## 5. Exclusions and what remains missing for C4

Excluded: all 1/4/16 GiB or larger tiers, beyond-RAM/cold-cache work, archive-entry
stress (M6), deliberate process kills (M7), disk filling (M8), mounting or exercising
multiple filesystems (M9), staging/restore-envelope experiments (M10), PostgreSQL
or NAS/USB/network access, real inputs/keys and any change to the 64 GiB constant.
The single existing filesystem is an environment selection, not an M9 matrix.

Even a later successful pilot and M5 check would **not complete C4**. The wider
plan still needs archive/interruption/disk-full/filesystem evidence, an appropriate
I/O-bound tier or an explicit limitation, the restore-size ratio/working space,
real growth and available-disk inputs, a chosen margin and a separately approved
operational ceiling. M10 and clean-host recovery retain their later restore-spec
authorization boundary. Do not silently substitute this pilot for that missing
envelope or change the owner's sequencing to make a task appear complete.

## 6. Future approval fields and blank evidence template

| Approval field | Present disposition |
|---|---|
| Owner approval/reference and run window | **PENDING — no campaign or M5 permission** |
| Exact execution revision | **PENDING**; this proposal inspected `00234cbec6bd76ab5ff8dcf128776c130c195c27` only |
| Private disposable environment / filesystem / enforcement references | **PENDING**; proposed numerical envelope is not a selected host |
| Operator, independent reviewer, stop/cleanup owner references | **PENDING** |
| Synthetic fixture producer/seed and key creation/use/disposal permission | **PENDING** |
| Instrumentation/controller and accounting/stopping-latency review | **PENDING** |
| Selected pilot and/or separately scoped M5 budgets | **PROPOSED above, not approved** |

No measured values are filled below; a dash means **not measured**, never zero.
This is a worksheet, not a valid `EvidenceLogEntry` instance or emitted result.

| Future observation | Value now |
|---|---|
| Run id, UTC timestamp, actual revision, `env_class=disposable-nonprod` | — |
| Private host/profile reference, actual RAM/swap/CPU, OS/kernel/Python tokens | — |
| Storage/device/filesystem/mount tokens; free space before/after | — |
| Dataset bytes/entry count/non-sparse allocation; generator/seed references | — |
| Command shape (`generate` or `verify`), repetition, cache state | — |
| Exit status/reason codes and opaque full-output reference | — |
| External wall time, tool elapsed time, RSS bytes, logical bytes/s | — |
| Sampled/group/block-I/O observations, precision, spread and anomalies | — |
| Operator/reviewer/cleanup references and disposal outcome | — |
| Disposition | No result exists; any future result must be `informational` |

The existing [closed evidence schema](../backend/app/recovery_governance/capacity.py)
requires real measured fields, constrained tokens and opaque references. Do not
populate it with invented zeroes/nulls, extra free text, archive object identifiers,
key material or embedded raw tool output. Store richer sampling/context privately
through referenced artifacts rather than adding undeclared schema fields. A valid
record would validate format only, not capacity or authority. Its required statement
remains **"informational; not an RPO/RTO or recovery-readiness measure"**.

## 7. Source review and preparation boundary

Read at the pinned source: [`Limits`](https://github.com/LYF-FC/local-assistant-core/blob/00234cbec6bd76ab5ff8dcf128776c130c195c27/backend/app/recovery_set/format.py#L64),
[`generate` and its two metadata scans around one content hash](https://github.com/LYF-FC/local-assistant-core/blob/00234cbec6bd76ab5ff8dcf128776c130c195c27/backend/app/recovery_set/generate.py#L77),
[`verify`](https://github.com/LYF-FC/local-assistant-core/blob/00234cbec6bd76ab5ff8dcf128776c130c195c27/backend/app/recovery_set/verify.py),
[`hash_member`](https://github.com/LYF-FC/local-assistant-core/blob/00234cbec6bd76ab5ff8dcf128776c130c195c27/backend/app/recovery_set/fsset.py#L363),
[test-only limit assertions](../backend/tests/test_recovery_set_fsset.py), and
the non-operational evidence/model schema above. The capacity model requires
restore/margin assumptions which this pilot cannot supply; do not fill them with
the pilot's resource caps and call the output validated.

Preparation used document/source inspection and arithmetic only. No key, fixture,
campaign, recovery command, resource observation, recovery/measurement test or
manual measurement-workflow dispatch was performed. Ordinary repository/document
checks and automatic documentation CI may accompany publication; they are not
capacity evidence. The runtime/source contracts are unchanged. This proposal and its
planning numbers supply no independent verification, Phase C/MVP acceptance,
real-set permission or operational status change.
