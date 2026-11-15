# Recovery-set key custody policy and key-generation requirements — spec 074 Phase C (C1, C5)

**Status: DRAFT design proposal for owner review. Nothing here is decided, implemented, operating or approved.** On 15 November 2026 the owner authorized Phase C design and preparatory work only; the owner later authorized implementation of the non-operational portions ([RECOVERY_PHASE_C_IMPLEMENTATION.md](RECOVERY_PHASE_C_IMPLEMENTATION.md)). This draft remains a proposal. No key exists or is created by this document; no person, medium or location is selected; no custody is activated; no tooling is implemented. This page distinguishes **design proposals** from **implemented controls**: the only implemented controls are those of [RECOVERY_SET.md](RECOVERY_SET.md). It changes no gate, register row or acceptance status. The frozen [spec 074](../specs/074-recovery-set-manifest/spec.md) is the authority for sections 6.1 to 6.7 cited below; this draft does not amend it.

## 1. What is fixed by the specification

- O1a (approved): a dedicated recovery-specific offline HMAC-SHA256 key, separate from every Work key, application secret, database credential and document key (spec 6.1). O1b (holder, custody, storage, access, backup, loss recovery) is deferred (spec 6.1, 10.2).
- **HMAC is symmetric (O6, spec 6.4).** Every holder of the verification secret can also create a valid MAC. The specification claims no separation of duties, no non-repudiation and no public-key verification. This draft claims none either.
- `generate` needs the secret on the host that runs it, so the generation host is a trust boundary (spec 6.5). The HMAC attests only that a key holder authenticated the manifest bytes at generation time.
- The key file is JSON of at most 2 KiB (`schema_version`, `purpose: "installation_recovery_set"`, `key_id`, `installation_id`, `created_at`, 32 bytes of material as 64 hex characters). It must be a regular, single-link file with no group or other permission bits, opened without following links, and never inside the set (spec 6.2; `backend/app/recovery_set/key.py`, `load_key`).
- Minimum custody responsibilities: spec 6.6, items 1 to 6. Rotation, replacement, loss and compromise consequences: spec 6.7. This slice provides no rotation, escrow, revocation or key-generation tooling.

## 2. Roles (design proposal; no person is named)

| Role | Responsibilities | Is a key holder? |
|---|---|---|
| **Primary key custodian** | Accountable owner of the primary key medium. Releases it for a recorded session, takes it back, keeps the key-event log. | **Yes. Can forge a valid manifest.** |
| **Recovery custodian** | Holds the independent recovery copy and acts only when the primary custodian is unavailable or on a compromise event. | **Yes. Can forge a valid manifest.** |
| **Operator** | Runs `generate` and `verify` inside an authorized session. Has the key **temporarily**, during that session, and must not retain it at rest. | Temporarily, for the session only. |
| **Independent fingerprint/hash-record keeper** | Holds the expected-fingerprint record and the expected-hash record ([RECOVERY_HASH_GOVERNANCE.md](RECOVERY_HASH_GOVERNANCE.md)). Appends; never overwrites. Holds no key and no set. | No. |

Assignments are **unresolved owner decisions**. The keeper must be a different person from both custodians, and the two custodians must be different people; if the household cannot supply that many distinct people, the owner must either accept a written, named degraded arrangement or defer real use. Whether one person may hold several roles is an owner decision.

## 3. What separation of duties does and does not provide

- Separation here is **procedural only**: role assignment, witnessed release, a log, and an independently held record. It is **not cryptographic separation**.
- **Both the primary and the recovery custodian are key holders and can each forge a valid MAC.** Adding the recovery custodian therefore increases the number of parties able to forge; that is the price of availability and must be stated in any approval.
- **The recovery custodian's second copy improves availability only; it does not protect authenticity against a compromised primary custodian.** Both holders possess the same symmetric HMAC key, so either can forge a valid manifest, and a compromise or defection of either one undermines every manifest under that key. A second copy helps if the primary medium is lost; it does not help if a holder is compromised.
- A custodian-run or operator-run `verify` is **not an independent verification**: the party running it holds the verification secret. No procedure in this draft provides independent HMAC verification, non-repudiation or public-key verification.
- The honest benefit is detective and deterrent: a substituted manifest is caught only if the independent records are intact and a later comparison is made, which with the current tooling is a key-holder-run `verify` ([RECOVERY_HASH_GOVERNANCE.md](RECOVERY_HASH_GOVERNANCE.md), section 3.1); a holder who also controls those records defeats it.

## 4. Storage design baseline and alternatives

**Design baseline (not an operational approval): an encrypted removable-media container, holding a filesystem the tool supports, stored in a physically separate location.** The supported-filesystem condition comes from the tool: the key file needs owner-only POSIX permission bits, and FAT/exFAT and many other removable filesystems fail closed (`RECOVERY_SET.md`, "Filesystem assumptions"). The container therefore needs a POSIX filesystem inside it, mounted at a fully resolved local path for the session (links are refused at every path component). A copy to a general disk or swap-backed memory can leave residue; whether that is acceptable is an owner decision (open issue K1).

| Option | Availability | Confidentiality | Recoverability | Operational complexity | Fit with the current tool |
|---|---|---|---|---|---|
| **A. Encrypted removable container (baseline)** | Moderate; needs physical retrieval, no online dependency | Strong if the passphrase is held apart from the medium | Good with a second, independently stored copy (the recovery custodian's) | Low to moderate | Good once the container is mounted as a POSIX filesystem |
| B. Hardware token | High once in hand | Strong; the secret can be non-extractable | Weak; a lost or failed token cannot be duplicated unless the token supports it | Moderate | **Poor**: the tool reads a key file, not a token |
| C. Password-manager vault with break-glass entry | High | Depends on the vault host and its master secret, which can share fate with production | Good if the vault is backed up, which creates a second place to protect | Low to use, higher to govern | Needs export to a file for the session |
| D. Secret sharing (k of n) | Lower; needs k holders together | Strong against one holder | Good, but reconstruction is itself a procedure to rehearse | High; no tooling in the repository | The reconstructed key still lands as a file on one host |

## 5. Mapping to the six minimum responsibilities (spec 6.6)

| Item | Proposed control | Evidence |
|---|---|---|
| 1. Key and fingerprint record apart from each other and from the sets | Key on the custodian's medium, records with the keeper, sets on backup storage; no two in one location or container | Location inventory signed by the owner |
| 2. Accountable owner and a second recovery path | Primary custodian is the named accountable owner; the recovery custodian holds the second path | Role register; rehearsal record |
| 3. Protected at rest independently of the production host and backup storage | Encrypted removable container kept off both | Storage attestation |
| 4. Access limited, recorded, reviewable; use deliberate | Release only per event, with a log entry; no automated or scheduled use; review interval [owner decision] | Key-event log |
| 5. Recovery of the key rehearsed | Tabletop first (section 8); any live rehearsal needs separate authorization | Tabletop record |
| 6. Fingerprint record as independent as the hash record | Both held by the keeper under the same rules | Record-location inventory |

## 6. Rotation, replacement, loss and compromise (spec 6.7)

| Event | Proposed requirement | Spec 6.7 constraint kept |
|---|---|---|
| Planned rotation | Agreed date; a new key and a new independently recorded fingerprint; new manifests use it. Cadence is an owner decision. | Old manifests verify only under the old key and fingerprint, which must be retained while those manifests are in use (see [RECOVERY_RETENTION.md](RECOVERY_RETENTION.md) conflict CR3). No rotation command exists. |
| Replacement | Equivalent to rotation after damage, only if a copy exists. | No escrow mechanism exists; the recovery custodian's copy is the policy-level substitute. |
| Loss | Declare in the log. Authenticity of existing manifests can no longer be established; integrity against a manifest can still be checked and proves nothing about origin. The owner decides whether a set is re-validated from a known-good source and re-attested under a new key. | No key recovery and no unsigned bypass flag. |
| Compromise (suspected or confirmed) | Stop use; record the key as compromised in the keeper's register; treat every manifest under it as untrusted, including old ones, because a holder could have forged any; re-validate sets from known-good sources and re-attest under a new key with a new fingerprint record. Authority to declare is an owner decision. | No revocation list or online status; the register is manual. |

## 7. Threat model and residual risks (design level)

| Threat | Proposed mitigation | Residual risk |
|---|---|---|
| Theft of the medium | Encryption; passphrase held separately; off-site storage | Passphrase compromise or coercion |
| Key exposed on the generation or verifier host during a session | Dedicated minimal host, session log, removal after use (owner decision) | A compromised host during the session can attest anything (spec 6.5) |
| Custodian unavailable or lost | Recovery custodian and copy (availability only) | Both lost together if co-located |
| Compromised primary custodian | None from the second copy: both holders have the same key, so the recovery copy does not protect authenticity; the independent records and the compromise procedure of section 6 apply | The compromised holder can forge; detection depends on the independent records |
| A key holder forges a manifest | Independent hash and fingerprint records, compared | A forger who also controls the records; HMAC cannot prevent this |
| Key loss | Second copy and rehearsal | Gap until a new key is attested (spec 6.7) |
| Record tampering | Append-only, separately held records | Trust in the keeper |

## 8. Tabletop exercise (synthetic material only)

No key is created or used. A placeholder card marked "SYNTHETIC PLACEHOLDER, NOT A KEY" stands in for the medium; identifiers are obviously fake (for example `00000000-0000-4000-8000-000000000000`). The exercise is a discussion and paper walk-through, runs no tool and creates no file shaped like a key.

| # | Scenario | Pass criteria |
|---|---|---|
| T-1 | Planned release for a generation session | Complete log entry; medium returned; host-residue checklist complete |
| T-2 | Primary custodian unavailable; recovery custodian acts | Recovery path followed without the primary copy; authorization recorded |
| T-3 | Primary medium lost | Second copy located; re-copy plan identified; owner informed |
| T-4 | Suspected compromise | Declaration, register entry, quarantine of manifests and re-attestation plan produced |
| T-5 | Fingerprint record disagrees with the key | Use stops; the dispute route of the hash-governance design is followed |
| T-6 | Session aborted midway | Medium returned; aborted session logged; any `.recovery-set-tmp-*` file handled per `RECOVERY_SET.md` |

The record notes date, roles present, outcome per scenario, gaps and follow-up owner. It is a document, not evidence of operational recovery readiness.

## 9. C5: key-generation requirements (requirements preparation only)

Key generation is deferred until the custody decisions of section 10 exist; these requirements are a preparation draft and cannot be finalised before then. These are requirements and design preparation only: no tool is implemented, no key is generated, nothing is provisioned, and key-generation tooling and any provisioning workflow remain unauthorized (O9).

| ID | Requirement | Objective acceptance check |
|---|---|---|
| KG-1 | 256 bits from the operating system's cryptographically secure random source; never derived from a passphrase, timestamp, counter or user input; no seeded or deterministic mode | Review of the source; a test that the generator calls only the OS source |
| KG-2 | Fail closed if the source is unavailable or returns fewer bytes than requested; no fallback source | Fault-injection test: short read and exception both produce no key file |
| KG-3 | File format exactly as spec 6.2; fresh random `key_id`; `installation_id` supplied explicitly by the operator, never read from the database; `created_at` in the specified form | Round-trip through the existing key model; mismatch cases rejected |
| KG-4 | Keyed fingerprint computed as spec 4.2 and emitted separately, never inside the key output, for recording by the keeper before first use | Fingerprint equals the recomputed value; absent from the key file path output |
| KG-5 | Exclusive creation, owner-only mode at creation, no overwrite or replace, to a path chosen by the custodian outside any recovery set | Existing target refused; created mode has no group or other bits |
| KG-6 | Material never printed, logged, placed in an argument or environment, or included in an exception, repr or traceback | The same absence tests as spec 6.3, over every output stream and log |
| KG-7 | Durable and atomic: flush the file and its directory; an interruption leaves no partial key file | Kill-point tests (synthetic) |
| KG-8 | Metadata-only generation record (key id, an opaque reference to the keeper's fingerprint record, creation time, installation id, ceremony identifier, role), never the material and never the 64-hex fingerprint itself, which cannot be told apart from key material by syntax | Record schema review; absence tests |
| KG-9 | Lifecycle states generated, provisioned, active, rotated, retired, destroyed, each transition logged and tied to the retention matrix | State table and transition tests |
| KG-10 | Generation happens only in a custodian-authorized session on a host the custodian designates; a second copy is a second holder and is logged as such | Procedure review; tabletop |
| KG-11 | Two generations never yield the same key or `key_id` | Test with synthetic runs only |

Failure modes to be covered: short or failed random read, existing target, insecure target mode or filesystem, interrupted write, full disk, fingerprint record not made before first use, duplicate custody copy not logged. All tests would use synthetic material only and run only after a separate authorization.

## 10. Owner decisions required (unresolved)

1. The people for each role, and whether one person may hold several.
2. The storage option and the physical locations of the primary and recovery copies; whether the medium baseline is accepted.
3. How the key file is presented to the tool from the medium (K1).
4. Whether a minimal dedicated session host is required.
5. The key-event log review interval, the rotation cadence and the authority to declare compromise.
6. Whether the degraded arrangement is acceptable when too few distinct people exist.
7. Whether key-generation tooling is wanted at all, or a documented manual ceremony is preferred.
8. Whether public-key signatures are required, which would revisit O6 (spec 6.4).

## 11. Objective acceptance criteria for this document

- Each of spec 6.6 items 1 to 6 and each row of 6.7 maps to a named control and an evidence artifact.
- The text states that HMAC allows every secret holder, including both custodians, to forge, and that separation is procedural only.
- The operator's key access is stated as temporary and non-retained.
- Every role is an owner decision with no person named; no key, medium or custody arrangement is activated.
- The tabletop uses synthetic material only.
- Nothing claims the policy is operating, approved or tested on a real key.

## 12. Out of scope

Generating, provisioning, storing or rotating a real key; key tooling; creating or operating a real recovery set; operational recovery; changing `spec.md`, the manifest format or `app/recovery_set`; any change to Gates 6, 10, 11, OPS-09 or OPS-10.
