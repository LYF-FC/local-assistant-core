# Recovery key manual ceremony — procedure draft for review

**DRAFT; blocked from execution.** Prepared 19 November 2026 against `00234cbec6bd76ab5ff8dcf128776c130c195c27`. The owner approved the manual-ceremony **requirements direction** on 18 November and subsequently authorized preparation of this planning-only procedure. Neither decision authorizes a ceremony, key generation (including synthetic keys), provisioning, media mounting, key use or dedicated tooling. This document contains future steps for review, not an executable recipe. No recovery/key-generation command, RNG call, fingerprint computation or ceremony test was run to prepare it; work was limited to source/document inspection and editing.

[PROJECT_MASTER.md](../PROJECT_MASTER.md) owns scope/status. The [scoped owner decision](../DECISIONS.md#18-november-2026--spec074-c1c3-design-c4-planning-and-c5-manual-ceremony-requirements-approved), [remaining worksheet](SPEC_074_OWNER_DECISION_WORKSHEET.md), [custody requirements](RECOVERY_KEY_CUSTODY.md#9-c5-key-generation-requirements-requirements-preparation-only) and [Spec 074 sections 4.2 and 6](../specs/074-recovery-set-manifest/spec.md) govern this proposal. No C1–C5 task, Phase C, Spec 074, independent verification or MVP acceptance is completed here.

## 1. Execution gates — all currently unmet or pending review

The future operator must stop before handling a key unless **all** gates below have explicit evidence and the owner has separately authorized the exact operation. A blank field is a blocker, not discretion. Public records carry role names and opaque evidence references only; actual identities, host/path/media/location details and inventories belong in separately authorized private records, never Git.

| Gate | Required decision/evidence | Current state |
|---|---|---|
| G1: authority and custody | Owner authorization naming scope; private assignments for primary/recovery custodians, operator, keeper and witness; independent authority check of the decision | PENDING; no execution authorized |
| G2: session and storage | Custodian-designated host; supported POSIX filesystem; separate encrypted removable containers/locations; passphrases apart from media; key presentation, host/swap/residue, access/abort/cleanup controls | PENDING; no medium or host selected/mounted |
| G3: reviewed manual method | Identified OS cryptographic random utility/API and version; independently sourced random key ID; protected input/output transport; exact-format construction; exclusive, no-follow, durable atomic publication; bounded protected readback | PENDING; no approved end-to-end manual recipe |
| G4: fingerprint bootstrap | Reviewed implementation/method of the existing keyed-fingerprint algorithm, separate keeper handoff and record comparison, with secret-handling evidence | PENDING; no approved ceremony-facing method |
| G5: validation and failure evidence | Separately authorized synthetic negative/kill-point/absence tests of the exact G3/G4 method on the intended filesystem; reviewed results and KG-11 distinct-output/duplicate-control evidence | PENDING; no test authorization or new evidence |
| G6: records and lifecycle | Private event/copy-inventory procedure, owner-approved numeric retention/review/rotation intervals, destruction authority/evidence, incident and recovery-rehearsal rules | PENDING; design relationships alone supply no numeric periods |
| G7: ceremony execution authority | Owner authorization for the precise future ceremony plus custodian-authorized session, confirming G1–G6 evidence/revision and stop authority | PENDING; cannot be inferred from this draft's approval |

Primary and recovery custodians must be different people; the keeper must differ from both and hold no key or set. Use a separate witnessing role under the approved recording process. Operator access is temporary; any role overlap needs a specific owner decision, with no degraded arrangement inferred. Both custodians can forge HMACs. The recovery copy improves availability only; it does not protect authenticity against a compromised holder. Witnessing is procedural and is not independent HMAC verification.

## 2. Exact output contract and secret boundaries

The future protected key file must be a closed JSON object of at most **2048 bytes**, with exactly these fields; this table is a contract, not a populated key template:

| Field | Required value/shape |
|---|---|
| `schema_version` | Integer `1`, not Boolean or string |
| `purpose` | Literal `installation_recovery_set` |
| `key_id` | Fresh random canonical lowercase hyphenated UUID, produced independently of key material; never derived from the material or reused intentionally |
| `installation_id` | Explicit operator-supplied canonical UUID from the independently approved private identity record; no database lookup or automatic discovery |
| `created_at` | Actual creation time in valid UTC `YYYY-MM-DDTHH:MM:SSZ` form |
| `material` | Exactly 32 bytes from the approved OS cryptographic random source, encoded as 64 lowercase hexadecimal characters; no passphrase/time/counter/user-derived or seeded substitute |

No duplicate/unknown fields or invalid values. Protected readback must meet [`load_key`](../backend/app/recovery_set/key.py) and [`read_protected_file`](../backend/app/recovery_set/fsset.py) rules: regular file, exactly one hard link, current effective-user ownership, owner-readable, **no group/other permission bits**, bounded read, and no-follow opens for the file and every path component. Use a reviewed owner-read/write-only creation mode (0600) rather than creating broadly and restricting later. Store outside every recovery set. A preflight path inspection alone is insufficient against replacement races; the reviewed write/read method must enforce its protections at the operation.

Secret material must never enter arguments, environment values, terminal output, shell history, logs, tracebacks, command substitution, clipboard, screenshots, chat, tickets, public artifacts or Git. Do not manually type/copy the secret through a text editor or a general temporary file. Approved secret transport must remain within the reviewed protected process/file boundary, including its error paths. Disable or exclude recording, crash dumps, indexing, sync and backup exposure according to G2's reviewed host policy; do not claim that cleanup proves physical erasure or absence of swap residue. Unresolved residue controls block execution.

## 3. Future sequence — descriptive only, do not execute

1. **Authorize and witness the session.** Primary custodian and operator verify G1–G7 and the keeper/witness availability against private records. Record ceremony/authority references and the exact approved method revision. Agree a bounded session end and abort owner. No key operation begins if any gate or private assignment remains unresolved.
2. **Prepare the approved boundary.** In that future authorized session only, the custodian would present the approved media/container on the designated host. Operator and witness would confirm protected destination, independent record channel, supported filesystem and residue controls using the reviewed method. Reject existing targets, links/aliases, unsupported permissions or unapproved storage. No production, NAS, database or recovery-set access is needed or included.
3. **Create identity and random material under G3.** Operator would explicitly enter only the approved non-secret installation identity/metadata. The approved OS method would obtain exactly 32 secret bytes and a separately generated random UUID. A failed/short random read must stop without a published key; there is no fallback, truncation/padding or reuse. Neither witness nor keeper should receive secret bytes.
4. **Publish protected output under G3.** The method would construct the exact JSON within the protected boundary, create a private exclusive temporary file on the approved filesystem, write completely, flush/synchronize that file, publish atomically without replacing an existing destination, remove any temporary alias and synchronize the containing directory. Before success, final output must have one link and pass protected readback. The reviewed recipe must specify crash states and cleanup for every intermediate file/link and any uncertainty after publication. A shell redirection, editor save or ordinary overwriting rename is not accepted as proof. No such recipe is selected or validated here; absent that evidence, stop at G3.
5. **Compute and independently retain the fingerprint under G4.** A separately approved method would compute the keyed fingerprint from the protected file and emit only the fingerprint to the keeper's approved separate channel. The keeper would record and witness-compare it before any first use. Do not place it in the key JSON or metadata event log. If the keeper's record is missing/disagrees, stop; never bootstrap the expected value from a recovery manifest or an ungoverned tool display.
6. **Record generation without activating.** Custodian/operator would append the generation event and evidence references after confirmed publication and fingerprint handoff. The record must not claim provisioned/active merely because the file exists. The keeper would retain the separate fingerprint record independently of the key, set, manifest and verifier host.
7. **Handle the second copy only if explicitly in scope.** A future separately authorized provisioning/copy step would need the same protected transport, exclusive durable-write/readback and fingerprint comparison controls on the recovery custodian's approved medium. The copy is of the same key, not another generation. Log the second holder and copy inventory; do not create an unlogged copy or extra holder. Without that permission, do not copy or claim the recovery path exists; an incomplete required recovery path blocks activation.
8. **Close or abort the session.** Custodians would account for every approved copy and temporary artifact, return media and remove temporary operator access under G2, and append actual outcomes. Record uncertainty/incidents without secret values. Do not activate/use a key, run recovery `generate`/`verify`, rehearse recovery, rotate, destroy or restore anything unless those exact later actions have separate authority.

### Fingerprint bootstrap detail

The existing algorithm is `HMAC-SHA256(material, FINGERPRINT_DOMAIN || canonical(public_identity))`, with `FINGERPRINT_DOMAIN` equal to the bytes `butler.installation-recovery-set-key-fingerprint.v1` followed by one newline. `public_identity` contains exactly `key_id`, `purpose`, `installation_id`, `created_at`. [`canonical`](../backend/app/recovery_set/format.py) uses sorted JSON keys, compact comma/colon separators and the repository's JSON encoding; [`KeyFile.fingerprint`](../backend/app/recovery_set/key.py) returns lowercase hexadecimal. The secret keys the HMAC and is excluded from the serialized identity. An unkeyed digest of metadata is not a substitute.

These existing library functions identify the algorithm; they are **not** an approved manual execution interface or a key-generation tool. Current recovery `generate` and `verify` require an externally supplied expected fingerprint, and `verify` also needs a manifest/set. They cannot establish that initial independent anchor. No fingerprint-only CLI flag/command exists here, and none is invented. G4 requires a reviewed separate method and safe handoff; authorizing its design or implementation, if needed, is another bounded decision. The expected value must come from the keeper's independently governed ceremony record, not be read back from the same presented key/manifest as its own trust anchor.

## 4. KG-1–KG-11 traceability and evidence gates

All evidence in this table is **required future evidence, not a claimed result**. Tests involving synthetic keys, randomness, file publication or failure injection remain unauthorized by this document.

| Requirement | Future responsible roles / control | Evidence required before release |
|---|---|---|
| KG-1: OS cryptographic randomness | Operator uses reviewed OS source only; method reviewer checks source/version | G3/G5: source review, call-path evidence, no seed/fallback/input-derived source |
| KG-2: fail-closed random reads | Operator aborts on exception/short read | G5: fault injection proves no published key and protected cleanup on both failures |
| KG-3: exact format and binding | Operator supplies installation UUID; witness checks approved metadata | G3/G5: protected model round-trip, invalid/mismatch rejection, independent key-ID generation evidence; no DB lookup |
| KG-4: separate keyed fingerprint | Operator computes via approved method; keeper records, witness compares before use | G4/G5: algorithm comparison, safe separate output/handoff, no fingerprint field in key JSON or mixing with key-path output |
| KG-5: protected exclusive output | Custodian chooses destination outside sets; operator uses approved writer | G3/G5: no-overwrite, no-follow/path-race, ownership/mode/single-link and unsupported-filesystem rejection evidence |
| KG-6: absence of secret disclosure | Operator controls host/transport; reviewer examines all paths | G2/G5: stdout/stderr/log/exception/traceback/argument/environment and written-artifact absence evidence, including crashing cases; review terminal/history/clipboard controls |
| KG-7: durable atomic publication | Operator follows validated filesystem-specific recipe | G3/G5: file and directory synchronization evidence, kill points before/during/after publication and alias removal; no partial final file; failure cleanup and durability-uncertainty handling |
| KG-8: metadata-only record | Custodian/operator log, keeper owns separate fingerprint record | G6: record review and absence tests; only opaque fingerprint-record reference in events, never material or 64-hex fingerprint |
| KG-9: lifecycle audit | Custodians approve transitions; keeper maintains relevant records | G6: reviewed state table/transition evidence and numeric retention policy; generated/provisioned/active/rotated/retired/destroyed kept distinct; actual operations logged only when performed |
| KG-10: controlled session/copies | Custodian authorizes; operator temporary; recovery custodian accountable for copy | G1/G2/G6/G7: session authority, role separation, inventory, return/abort controls and separately authorized tabletop/rehearsal evidence |
| KG-11: distinct generations | Method reviewer documents separate OS random draws and reviewed duplicate-control/evidence handling | G5: the existing distinct-output requirement and separately authorized synthetic checks remain required. Finite checks can detect repeated outputs but cannot prove collision absence for all future generations. This draft supplies no reviewed secret-safe duplicate-control method or validation evidence and does not claim KG-11 satisfied |

The missing reviewed method/evidence is part of the existing G3–G5 execution-readiness gaps, not a new requirement to prove universal uniqueness or a change to Spec 074's acceptance criteria. Do not build a registry of raw secrets or publish material/fingerprints as a shortcut to a uniqueness claim. Any proposed collision-control method must preserve KG-6/KG-8 and receive separate review. This document changes neither the requirement nor its acceptance criterion.

## 5. Failure and incident disposition

| Failure | Required future response / evidence |
|---|---|
| Short or failed random read | Stop; no fallback/reuse and no final key; record non-secret failure code/reference; G5 evidence required |
| Existing destination or random-ID conflict | Refuse overwrite/replacement; stop for reviewed resolution without exposing material; log actual outcome |
| Unsafe file mode/type/owner/link/path/filesystem | Stop before creation/use; do not repair silently or weaken validation; record opaque failure reference |
| Interrupted write, publication or synchronization | Treat as failed/uncertain, never active; account for final/temp paths privately; custodian controls quarantine/cleanup under approved plan; no automatic retry using partial material |
| Full disk or any I/O error | Stop without claiming durable publication; account for protected remnants; filesystem-specific evidence must cover full disk, not just injected generic I/O error |
| Fingerprint missing, wrong, leaked into event log or not independently recorded | Block first use; correct via approved append-only incident process; do not replace the expected record with a presented manifest's value |
| Unlogged duplicate copy/holder | Stop; reconcile private copy inventory and treat exposure as suspected compromise pending authorized disposition |
| Secret disclosure, unexpected access, host/residue uncertainty | Stop; alert the designated custodian/incident authority through approved private process, with no secret in report; do not claim cleanup reverses compromise |

Loss/compromise follow [Spec 074 section 6.7](../specs/074-recovery-set-manifest/spec.md): a lost key prevents authenticity checks; suspected compromise makes all manifests under that key untrusted, including old ones. Revalidation/re-attestation, replacement and rotation are future separately authorized work. Key destruction is not erasure of backup data. No unsigned bypass or self-anchoring exception is proposed.

## 6. Record shape, review outcome and remaining decisions

The generation evidence package would contain ceremony/date/time, exact method/code revision, authority/session references, role references, installation/key IDs, gate evidence references, outcomes and incident/cleanup/copy-inventory references. Private details stay private. The [`KeyEventRecord`](../backend/app/recovery_governance/custody.py) portion is metadata-only: event ID/type, key ID, opaque fingerprint-record reference, installation ID, occurrence date, role/actor and optional ceremony reference. It has no generation-time timestamp field beyond its date; a separately governed ceremony record would retain the exact creation/session time without changing that interface. Never put material or the 64-hex fingerprint in this log. The keeper's fingerprint record is a separate controlled artifact, not a public attachment.

`FutureKeyOperations` is a protocol only; the library validates records and does not verify owner authority, implement lifecycle transitions or perform key operations. Format-valid references are not approvals. No interface completion, state-machine implementation or validator result can release G7.

The owner/reviewer can now approve or amend this **procedure draft** and assign follow-up design/evidence work, while keeping execution unauthorized. Remaining material decisions are actual custody/session/storage/residue controls; numeric retention/review/rotation intervals; the exact OS randomness and exclusive durable-write method; the initial fingerprint computation/handoff method; separately authorized negative-test evidence; and reviewed KG-11 duplicate-control/evidence handling. An approved manual direction does not establish that an end-to-end manual method is feasible or operationally ready. If existing OS utilities cannot safely satisfy these requirements together, stop and request a separately scoped method/tooling decision rather than improvising a secret-generating one-liner.

This preparation changes no task box, reviewer record, gate, status, frozen requirement or runtime. C5 remains open; C1 custody activation and other Phase C outcomes remain absent. C4 measurement authorization is separate. Restoration/staging remain reserved for Spec 075, without implementation or recovery authorization here.
