# Recovery-set capacity and resource validation plan — spec 074 Phase C (C4)

**Status: DRAFT test plan for owner review. No capacity measurement has been run, and none is authorized.** On 15 November 2026 the owner authorized Phase C design and preparatory work, then separately authorized implementation of the non-operational portions; the model-only capacity calculation was merged in PR #43 ([RECOVERY_PHASE_C_IMPLEMENTATION.md](RECOVERY_PHASE_C_IMPLEMENTATION.md)). This draft remains a proposal; the calculation is not a measurement or capacity validation. This plan authorizes no capacity measurement, no large-data run, no NAS or production-storage access and no synthetic-key test execution. The **64 GiB dump ceiling is an unapproved placeholder** (`PROVISIONAL_UNAPPROVED_DUMP_CEILING_BYTES` in `backend/app/recovery_set/format.py`, spec 3.8, 10.1) and is not changed here. Thresholds below are **hypotheses to test**, not acceptance criteria; the owner decides criteria and the real ceiling separately after measured evidence exists. No result of this plan will be an RPO/RTO measure (O3). No gate or status changes.

## 1. Environment (disposable, non-production)

- **Permitted:** a dedicated disposable VM or container, or a scratch directory on a local disk of a disposable host; synthetic data only; no network needed.
- **Not permitted:** the NAS, any production host or storage, any host holding real data or a real key.
- A hosted CI runner may serve the small tiers only; its variability (shared hardware, throttled disks) makes it unrepresentative of the NAS.
- Any run needs a synthetic key file. The only helper is test code (`backend/tests/recovery_set_support.py`); whether using it outside the test suite for measurements is allowed is an owner decision and is not assumed.

## 2. Capacity model (what must fit, not only the dump)

The tool streams the dump with a 1 MiB buffer and writes only the manifest (limit 4 MiB), so its own footprint is small (spec 3.8). A ceiling that supports **recovery** must nevertheless consider the whole envelope. Symbols: D = dump size, A = archive payload (existing limit 64 MiB), M = manifest (at most 4 MiB), R = restored-database size divided by D (**unknown; must be measured**, not assumed).

| Component | Size | Source |
|---|---|---|
| Source dump on backup storage | D | the set |
| Archive objects | A (at most 64 MiB; at most 8192 entries) | existing limits |
| Manifest plus its temporary link during publication | M, one inode until the temporary link is removed | `publish.py`; `RECOVERY_SET.md` |
| Staged copy of the verified set on the recovery host | D + A (staged-restore principle, spec 8; the tool does no staging) | spec 8 |
| Restored database | R × D, plus index, WAL and temporary sort space during `pg_restore` | unknown factors |
| Free-space safety margin | owner decision | none yet |

Required available space on the recovery host is therefore at least D + A + M + (R × D) + restore working space + margin, evaluated for the **real** host, not for the tool. Time includes hashing the source (1 pass), copying to stage (1 pass), re-hashing the staged copy if the principle is applied (1 pass) and `pg_restore`; passes multiply I/O. None of R, restore working space, available disk on a real recovery host or the real database size is known; unknown stays unknown.

## 3. Measurements

| ID | Measure | Method | Hypothesis (not a criterion) |
|---|---|---|---|
| M1 | Hash throughput versus size | Non-sparse synthetic files at 1, 4 and 16 GiB; at least three runs per tier; larger tiers only if separately approved | Time roughly linear in size (spec 3.8) |
| M2 | Peak resident memory | Sample the process during `generate` and `verify` | Roughly flat, independent of D |
| M3 | Wall time | Same runs; report median and spread | Informational (`elapsed_ms` is informational only) |
| M4 | Disk use of publication | Free space before, during and after | Transient overhead about M |
| M5 | Size-boundary logic (not a capacity measurement) | Use small injected limits and fixtures at limit minus 1, equal and plus 1. Only a dump above the configured limit should produce `set_size_limit_exceeded` from metadata (`fstat`) before hashing; otherwise-valid dumps below or equal to the limit may proceed to hashing | Above limit: rejection before hashing, nothing published. Below/equal: no size rejection; other validation still applies. This establishes boundary logic, not capacity |
| M6 | Archive-entry stress | Archives of 1, 100, 4096, 8192 and 8193 entries of small objects | 8192 entries fit under the 4 MiB manifest limit (spec estimate about 1.4 to 1.6 MB); 8193 refused |
| M7 | Interruption | SIGKILL during hashing, during temporary write and after the link before cleanup (extending the T27 to T31 behaviour on a real disk) | No partial final manifest; stale temporary reported |
| M8 | Disk-full | A deliberately small scratch filesystem filled during manifest write | Fails closed, no final manifest. **Not covered by the existing tests**, which inject `EIO` and do not exercise `ENOSPC` |
| M9 | Filesystem matrix | ext4, XFS, btrfs, tmpfs and overlayfs on the disposable host; FAT/exFAT expected to fail closed. No NAS or network filesystem | Capability detection and `filesystem_unsupported` per spec 9.1 |
| M10 | Staging and restore envelope | R, restore working space and time on a disposable PostgreSQL with synthetic data | Unknown; the point is to measure R |

## 4. Variability and limitations of the proposed tiers

- **1, 4 and 16 GiB tiers can fit in the page cache** of a typical disposable host. They then mostly measure CPU hashing, not storage, and warm repeats are misleadingly fast. At least one tier larger than host RAM, or a controlled cold-cache procedure, is needed for I/O-bound behaviour; that may be infeasible on a small disposable host and is an owner decision.
- **Three points cannot show non-linearity.** Throttling, burst-credit exhaustion on virtual disks and cache cliffs can appear beyond 16 GiB; a linear extrapolation to 64 GiB or beyond is unsupported evidence.
- **Sparse allocation does not make hashing cheap.** A sparse dump near the 64 GiB placeholder, below or equal to the configured limit, may proceed to hashing and trigger substantial logical reads. Those reads do not establish representative physical I/O. M5 boundary logic should instead use small injected limits and fixtures, separately from capacity measurements; use non-sparse data for M1 to M3. The 64 GiB operational ceiling remains unapproved.
- **Noisy neighbours, CPU frequency, concurrent load and filesystem aging** change results run to run; report spread and host load, not a single number.
- **Synthetic data** is neither a real dump nor a real archive; compressibility of the content does not affect hashing but does affect copy and restore times.
- **A passing run shows behaviour on that environment only.** It validates no real host, real storage, NAS or recovery objective.

## 5. Metadata to record

A reference to the host or VM profile (model and CPU description are kept in that referenced record, not in the log), CPU cores, RAM, swap, kernel, operating system and Python version as constrained version tokens, git SHA under test, storage device type and filesystem type from closed lists, mount options from a closed list, free space before and after, cache state, dataset descriptor (size, opaque generator and seed references, sparse or not, entry count), an opaque reference to the stored tool output together with its exit status and reason codes, operator and reviewer roles. Verbatim tool output and free-text descriptions are **not** embedded in the log, so an entry cannot become a channel for arbitrary data.

## 6. Evidence-log entry (JSON lines; synthetic data; no key material or real paths)

```
{ "run_id": "<ref>", "date_utc": "<complete UTC or offset timestamp>", "git_sha": "<40 hex>",
  "env_class": "disposable-nonprod",
  "host": {"profile_ref": "<ref>", "cores": 0, "ram_bytes": 0, "swap_bytes": 0,
           "kernel": "<token>", "os": "<token>", "python": "<token>"},
  "storage": {"device_type": "<closed list>", "fs_type": "<closed list>",
              "mount_options": ["<closed list>"], "free_before": 0, "free_after": 0},
  "dataset": {"size_bytes": 0, "generator": "<ref>", "seed": "<ref>", "sparse": false, "entries": 0},
  "cache_state": "cold|warm|unknown", "command_shape": "generate|verify",
  "tool_output_ref": "<ref>", "tool_exit_status": 0, "tool_reason_codes": ["<code>"],
  "measurements": {"wall_ms": 0, "peak_rss_bytes": 0, "throughput_bytes_s": 0},
  "anomalies": ["<code>"], "operator": "<ref>", "reviewer": "<ref>",
  "disposition": "informational" }
```

Each entry carries the statement "informational; not an RPO/RTO or recovery-readiness measure". Nothing is classed "measured operational capacity" until the owner decides (spec 3.8).

## 7. Results template

One row per run: run id, date, code SHA, environment class, dataset, M1 to M10 values with spread, tool output reference, anomalies, disposition. Hypotheses are listed beside results as "supported / not supported / inconclusive", never as "passed".

## 8. Evidence needed for a future dump-ceiling decision

A completed matrix on a named disposable environment, including a tier beyond host RAM or a stated reason it is absent; observed time per GiB with spread; memory behaviour; archive-entry results; interruption and disk-full results; the measured R and restore working space; the real database size and its growth (the owner's input); the real recovery host's available disk (the owner's input); and the owner's proposed margin. The ceiling is then a separate owner decision (spec 10.2, O8).

## 9. Owner decisions required (unresolved)

Whether and when any measurement is authorized; the disposable environment; whether a synthetic key may be created for runs; larger tiers; acceptance criteria and thresholds (after evidence); the safety margin; the real ceiling.

## 10. Objective acceptance criteria for this document

Each measurement has a procedure, a recorded environment, a stated limitation and a hypothesis labelled as such; the capacity model covers staging, temporary, restore and available disk; no threshold is presented as approved; no measurement is run or claimed.

## 11. Out of scope

Running anything; NAS or production access; destructive or production-scale tests; changing the 64 GiB constant; RPO/RTO claims; changing `spec.md`.
