# Expected-manifest-hash governance — spec 074 Phase C (C2)

**Status: DRAFT design proposal for owner review. No control described here is implemented, approved or operating.** On 15 November 2026 the owner authorized Phase C design and preparatory work only; the owner later authorized implementation of the non-operational portions ([RECOVERY_PHASE_C_IMPLEMENTATION.md](RECOVERY_PHASE_C_IMPLEMENTATION.md)). This draft remains a proposal. The only implemented behaviour is that of [RECOVERY_SET.md](RECOVERY_SET.md): `verify` accepts an optional `--expected-manifest-hash`, compares it with the computed `manifest_hash` after authenticity is valid, and a supplied mismatch always fails (spec 5.1, 5.2, 10.1; O5). Governance of the retained hash (who records, retains and updates it) is deferred (spec 10.2). Synthetic example values only. No status changes.

## 1. Purpose and the anchoring principle

A manifest must not be its own trust anchor (spec 5). The hash record exists so that an operator can supply a hash retained **independently of the recovery set, the manifest directory, the key storage and the verifier host** (spec 5.2). A match proves only that the manifest equals the supplied hash; it shows the manifest is the latest only if the source of the hash is independently governed (spec 5.2). The recovery set, a previous tool output, the database or the manifest itself are never the source.

## 2. Four acts that must not be conflated

| Act | Needs | Establishes | Does not establish |
|---|---|---|---|
| **Witnessing the recording of a manifest hash** | A person observing the entry being written | The entry matches what the witness saw | That the hash came from an authentic manifest, or that the displayed output was truthful (the generation host is a trust boundary, spec 6.5) |
| **Comparing the retained record with the generation output** | The record and the tool's printed output | The record equals what the tool printed for that run | That the host or the set was genuine |
| **Independently verifying the manifest's HMAC** | The verification key | That the manifest bytes were authenticated by a key holder | **Independence**: the party doing it holds the verification secret and could also forge (spec 6.4). Not a property any procedure below provides. |
| **Authenticating the identity and authority of the approver** | An out-of-band mechanism | That the approver is who they say and may approve | Anything about the manifest; no cryptographic mechanism for it exists in the repository |

A second person **cannot** independently rerun the HMAC verification without the verification key (`verify` requires `--recovery-key`). This design does not claim otherwise and does not add key holders: the key holders are those of [RECOVERY_KEY_CUSTODY.md](RECOVERY_KEY_CUSTODY.md) (both custodians, plus the operator temporarily).

**Cryptographic possibility versus existing tooling.** `manifest_hash` excludes the MAC (spec 4.2), so in principle it can be computed from the manifest alone, without the key. The repository has **no keyless command** for it: the commands are `generate` and `verify`, and `verify` reports `manifest_hash` only once authenticity is established. A keyless computation is therefore possible in principle and not available in practice; this draft does not rely on it and does not propose amending the frozen specification merely because no such command exists. If the owner ever wants one, it would be a separately authorized specification and implementation.

## 3. Options and trust implications

| Option | Description | Who must hold the key | Trust implications |
|---|---|---|---|
| **A. Witnessed record comparison (proposed baseline)** | The keeper records the `manifest_hash` from the generation output; a witness compares the entry with the output. | No one new | Detects transcription errors at the moment of recording. By itself it does **not** detect a later substitution of an older manifest: that needs a separate later comparison (section 3.1). Trusts the generation host, the operator and the witness. No HMAC statement is made by the record. |
| **B. Additional authenticity check by a key holder** | In an authorized session a key holder runs `verify`; the keeper records the reported `manifest_hash`. | The running holder, as already | Adds that an HMAC-valid manifest produced that hash. **The key holder is not an independent verifier**, and a custodian-run check is not independent. The keeper only observes. |
| C. Second verifier holds the key | Another person holds the key to verify independently. | One more holder | Real redundancy, but each additional holder can forge. Not proposed. |
| D. Keyless hash tool | A new command computes `manifest_hash` from the manifest. | None | Gives a second person an independent hash check (not an HMAC check). Needs its own specification; see section 2. |
| **E. Owner approval of the record** | The owner records approval of each entry through an out-of-band signature or witness process. | None | Authenticates the approver **only where that process is defined and trusted** (who signs, how a signature is checked, where it is kept); until then it adds nothing. The repository has no asymmetric signing library (spec 6.4, 12). |

### 3.1 Initial recording versus a later comparison

Two different comparisons must not be conflated.

1. **Initial witnessed recording and comparison (option A).** At generation time the keeper records the hash printed by the tool and a witness compares the entry with that output. This shows the record equals what the tool printed for that run. It says nothing about any manifest presented later.
2. **Later comparison of the retained hash against a presented manifest.** To learn whether a manifest presented later is the recorded one, its hash must be computed and compared with the retained entry. With the current tooling that computation is done by `verify`, which **requires the HMAC key** (`--recovery-key`) and reports `manifest_hash` only after authenticity is established; supplying the retained hash as `--expected-manifest-hash` makes a different manifest fail with `freshness_mismatch`. The party running it is therefore a **key holder**, so this later operation is a **key-holder check, not independent verification**: it detects substitution of an older or different manifest only if the retained record is intact and the key holder runs and reports the comparison honestly. No new tooling is proposed here.

Option A's baseline value is therefore the independently held record; the detection of a later substitution depends on the second, key-holder-run comparison.

Recommendation: A as the baseline; B as an optional additional check, described honestly as a key-holder check; E only once its process is defined and trusted; C and D are owner decisions outside this phase.

## 4. Record design (proposal)

- **Content, hash-only (spec 9.4 matter 3):** `manifest_hash`, `key_id`, installation UUID, schema head, set identifier, creation date, recorder, witness, approver, supersession pointer. No content, key material or archive object identifiers.
- **Independence:** held apart from the set, the manifest directory, the key storage and the verifier host (spec 5.2). The expected-fingerprint record is held to the same independence (spec 6.6 item 6); holding both in one place is permitted but their joint compromise together with the key defeats the anchor.
- **Append-only:** replacement is a new entry marking the old one superseded; the latest non-superseded entry for a set is the freshness reference.
- **Creation:** the operator transfers the hash from the generation output into the record during the authorized session; the witness compares (option A); an optional key-holder `verify` run adds option B.
- **Loss:** freshness reverts to `freshness_not_evaluated`; no match may be claimed.
- **Dispute (record versus manifest):** the record governs freshness only; the owner decides which set is authoritative. A record that disagrees with the key's fingerprint stops use (see the tabletop of the custody draft).
- **Rotation:** a key rotation adds a new fingerprint record; hash entries keep their `key_id`.

Synthetic example, illustrative only:

```
entry: 1   set_id: SYNTHETIC-SET-0001   key_id: 00000000-0000-4000-8000-000000000000
manifest_hash: 0000000000000000000000000000000000000000000000000000000000000000
installation: 11111111-1111-4111-8111-111111111111   schema_head: SYNTHETIC-HEAD
recorded_by: <role>  witnessed_by: <role>  approved_by: <role or none>  date: <date>  supersedes: none
```

## 5. Risks

The record is itself a point of trust. A record kept beside the sets re-creates self-anchoring. The operator can forget to append after a backup, leaving a stale reference (a deliberately supplied older hash matches an older manifest, spec 5.2). A holder who controls both the key and the record can forge a consistent pair.

## 6. Owner decisions required (unresolved)

Recorder, witness and approver; record medium and location; which options (A baseline; B and E optional; C and D excluded or not); the update procedure after each backup; whether freshness may be relied on before a second reviewer exists; who decides disputes; whether the out-of-band approval process for E is defined and trusted.

## 7. Objective acceptance criteria for this document

- The four acts of section 2 are distinguished and none is credited with more than the table states.
- It states that independent HMAC verification needs the key, that a key-holder check is not independent, and that the key-holder count is unchanged.
- It distinguishes the cryptographic possibility of a keyless hash from the absence of a command, and proposes no specification change on that basis.
- Each independence requirement of spec 5.2 maps to a control.
- The text distinguishes the initial witnessed recording from the later comparison of the retained hash with a presented manifest, and states that the later comparison needs the key and is a key-holder check.
- A demonstration that a substituted older manifest yields `freshness_mismatch` needs a synthetic key and a tool run; it is **not authorized** here and is not claimed.

## 8. Out of scope

Any tool that reads, writes or fetches records; a freshness service or "latest manifest" authority (spec 9.2); changing `spec.md`; synthetic-key runs; real hashes, keys or sets.
