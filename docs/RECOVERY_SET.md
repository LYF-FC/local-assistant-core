# Recovery-set manifest and offline verification — spec 074

**Status: synthetic-only implementation. Not verified, not merged, not accepted. No real key, real recovery set, operational use or recovery-readiness claim exists.** This page documents the `python -m app.recovery_set generate|verify` tool specified by the frozen [spec 074](../specs/074-recovery-set-manifest/spec.md). It changes no gate, register row or acceptance status (Gate 10, Gate 11 / MVP-05, Gate 6 / DOC-X02, OPS-09, OPS-10 are unchanged).

## What it establishes, and what it does not

The tool verifies the **integrity and authenticity of a defined backup set** against an authenticated manifest. It does **not** establish complete recoverability, successful restoration, configuration completeness, credential or key availability, or clean-host readiness. A set that verifies is not a complete or restorable recovery environment. The tool never connects to a database or a network, never parses the dump, never restores, and never writes inside the set.

A set is one directory containing exactly `database.dump` and, when an archive is declared, `archive/.archive.json`, `archive/.archive.lock` and zero or more `archive/<32 hex>-v<n>.original` objects. The manifest and the key live outside the set.

## Four separate results

`verify` always reports all four, and no later stage ever upgrades an earlier failure.

| Field | Meaning |
|---|---|
| `integrity` | The manifest is well-formed and canonical, and the set matches its recorded names, sizes and SHA-256 values under the closed-set rules. It says nothing about who made the manifest. |
| `authenticity` | A protected key file in the recovery namespace whose keyed fingerprint equals the independently supplied expected fingerprint, whose installation binding equals the installation the manifest declares, whose key references match the payload, and whose HMAC over the canonical payload verifies. |
| `expectations` | The independently supplied installation UUID, schema head and archive presence equal the manifest's authenticated declared values. |
| `freshness` | Only `freshness_not_evaluated`, `freshness_match` or `freshness_mismatch`. A match means the manifest hash equals the **supplied** expected hash and nothing more. |

Stage order: usage and trust-input shape, manifest read and structure, key and authenticity, expectations, set integrity, freshness. A malformed manifest or an invalid MAC can never receive a successful later result, and no expected-hash match is reported for either. A supplied expected hash that does not match always fails (exit 1), with or without `--require-freshness`; that flag only requires a hash to be supplied.

## Trust inputs

Every trust input is an explicit argument. There is no environment, configuration-file, default-path or same-directory fallback, and no value is taken from the manifest, the set, a database or a previous output.

| Argument | Required | Provenance |
|---|---|---|
| `--expected-key-fingerprint` | yes | recorded at key creation, separately from the key, the set and the manifest |
| `--recovery-key` | yes | protected key custody, never inside the set |
| `--expected-installation-id` (verify) / `--installation-id` (generate) | yes | an independently retained record, not read from the dump or database |
| `--expected-schema-head` (verify) / `--schema-head` (generate) | yes | the head the operator intends to restore |
| `--expect-archive present\|absent` | yes, on both commands | the operator's knowledge of whether an archive was provisioned |
| `--expected-manifest-hash` | optional | an independently governed record; its governance is not yet decided |

Exit statuses: `verify` returns 0 only when integrity is valid, authenticity is valid, expectations are met and freshness is not a mismatch; 1 for any other verification outcome; 2 for usage or trust-input errors (reported before any file is read). `generate` returns 0 only when `publication` is `published_durable`.

## Generation host and the HMAC limitation

`generate` needs the HMAC secret on the host that runs it, so **the generation host is a trust boundary**: whoever controls it can attest anything. The HMAC attests one thing: the manifest bytes were authenticated by a holder of the key at generation time. It does not show that the dump is genuine, complete, current or recoverable, or that the set was consistent when it was taken.

HMAC is symmetric, so **every holder of the verification secret can also create a valid manifest**. No separation of duties, non-repudiation or public-key verification is claimed. The declared installation identity and schema head are operator declarations authenticated by the key; they do not prove where the dump came from.

## Filesystem assumptions and compatibility

Specified for a local POSIX filesystem on Linux that gives `O_NOFOLLOW`/`O_DIRECTORY` opens, directory-descriptor-relative operations, trustworthy `fstat` results, `fsync` on files and directories and, for generation, a no-replace atomic primitive (a hard link that fails if the target exists). The tool cannot prove a filesystem honours these; it fails closed when an operation fails and makes no portability claim. Other media (FAT/exFAT, many SMB/NFS mounts, some USB filesystems) may fail closed: copy the set to a supported local filesystem, set owner-only modes deliberately and verify the copy.

Mandatory failures, never relaxed: symlinks and special files, nested directories, traversal, hard-linked members (`st_nlink != 1`), any group or other read or write permission on set members, `SET`, `archive/` and the manifest, and any group or other permission bit on the key file. The permission checks are a **local permission guard only**; there is no encryption, no protection once a copy leaves the filesystem and no confidentiality claim. A manifest names archive object identifiers and sizes and must be handled as sensitive operational metadata.

Archive quiescence is an operator precondition. A `.pending-*` object refuses both commands (`archive_pending_objects_present`), and `generate` reads the archive twice and refuses on any change (`archive_changed_during_generation`). A pass shows only that no change was observed.

## Publication and durability

`generate` writes an owner-only temporary file in the output directory, flushes it, publishes it with a single hard link that cannot replace an existing file, removes the temporary and flushes the directory. It never uses a replacing rename, a copy or a check-then-write fallback. `publication` is `not_published`, `published_durability_uncertain` or `published_durable`; only the last is success. If the directory flush cannot be confirmed the command fails (`publication_durability_uncertain`, exit 1) and leaves the possibly published file untouched. A retry fails with `output_exists`. Inspect the file with `verify`, make it durable outside the tool, or move it aside yourself. A temporary left by a killed run is a recoverable artifact: it is never deleted by a later run and is reported only through the informational note `stale_temporary_present`. If a killed run leaves a temporary that is still a hard link to the published manifest, that manifest has two links and fails the single-link rule until the operator removes the temporary.

## Limits

Archive entries 8192 (marker and lock included; the dump is one further member), archive object 128 KiB, archive payload 64 MiB and key file 2 KiB come from existing code. Manifest 4 MiB and the 1 MiB read buffer are provisional engineering limits. **The 64 GiB dump ceiling is an unapproved placeholder, not an approved or measured capacity.** The real ceiling needs measured resource testing and a separate owner decision, and no real set may be treated as supported by it. Tests exercise every limit through an internal, test-only function parameter with small synthetic fixtures; that parameter is not reachable from the command line, environment or any configuration file.

## Key custody responsibilities (holder and location not decided)

The key holder, storage, access procedure and loss recovery are deferred (O1b). Any future arrangement must at least: keep the key and its fingerprint record apart from each other and from the sets; have an accountable owner and a second recovery path; protect the key at rest independently of the production host and backup storage; limit, record and review access, with deliberate (not automatic) use for generation; rehearse key recovery; and retain the expected-fingerprint record as independently as the expected-hash record. Loss of the key means authenticity cannot be established for existing manifests; compromise means every manifest under that key is untrusted. This tool provides no key-generation command, rotation, escrow or revocation.

## Path overlap, public references and reporting order

- **`paths_overlap` is a path-shape check (exit 2, before any file content is read).** The manifest, key and output paths are compared with `SET` and with each other in two spellings: the lexical one (`.`, `..` and redundant separators removed) and the symlink-resolved one (existing symlinked components resolved, which touches path components only). A path that overlaps in either spelling, or a key and manifest that are the same existing file (for example by hard link), is refused. Lexical normalisation alone is **not** a symlink defence; the descriptor-relative, `O_NOFOLLOW` opens of the later stages are, and they still refuse a manifest, key or `SET` that is or becomes a symlink after this check. The check cannot close a race by itself: a directory swapped for a symlink between the check and the open is outside what a pre-check can establish.
- **`manifest_hash`, `key_id` and `key_fingerprint` are public references, reported once they have been computed from an authenticated manifest.** `verify` reports `manifest_hash` from the moment authenticity is established, including when expectations or set integrity then fail; it does not report it when the manifest could not be read or parsed or authenticity is invalid, because the tool then has no authenticated manifest to name. This is separate from `verified_references`, which is present only when integrity, authenticity and expectations all hold. Section 7.3 of the specification says "when computed" and does not require either choice; the tool takes the narrower one.
- **Only the first set-stage violation is reported.** Reasons are ordered: expectation reasons (installation, schema head, schema chain, archive expectation), then at most one set reason. Within the set stage the fixed detection order is `SET` mode, then entries in ascending raw byte-name order, then `archive/`, then the closed-set comparison, and only then hashing, so structure is always reported before hash mismatches. No count of further violations is emitted, because the closed output key set has no field for one.

## Verification is a point-in-time observation

A successful `verify` is an observation of the bytes read at that moment (`point_in_time` is always `true`). It does not guarantee that a later restore reads the same bytes. A later restore specification should restore from the exact staged copy whose bytes were verified. `verified_references` (set id, manifest hash, dump SHA-256 and members digest) is returned only when integrity, authenticity and expectations all hold, for that later specification to bind to. This tool performs no staging and no restoration, and `restore_performed` and `recovery_complete` are always `false`.

## Deferred, not decided here

Key holder and custody; governance of the independently retained expected hash; retention of manifests, backups and expected-hash records and forgetting reconciliation (a manifest listing a forgotten object is evidence about an old set only and never permission to restore it); the measured dump ceiling; real key-generation tooling; database binding of the installation identity; staged restore; clean-host rehearsal.

## Evidence boundary

The synthetic tests and the extended restore drill show that the implementation meets the specification on synthetic data in the environment where they run. They are not independent verification, real-key custody, real NAS/USB/network filesystem behaviour, clean-host recovery or an RPO/RTO measurement. Elapsed times printed by the tool and the drill are informational only.
