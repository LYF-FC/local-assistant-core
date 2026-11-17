# Temporary picomatch security patch

## Scope and authorization

On 17 November 2026 the owner authorized reviewing, testing and pinning the smallest
upstream fix in a separate draft PR, without hiding the advisory, bypassing npm audit,
changing statuses or merging. This package is development/build/test tooling only.
No application source, household data, provider or operational authorization changes.

The intended outcome is reproducibly installing picomatch 4.0.7 plus the single security
hunk from [upstream PR #254](https://github.com/micromatch/picomatch/pull/254),
commit `c63a5bf4e61dbdb81bc41e97dc2616c30acce337`.
The upstream PR is unmerged and is not an official fixed release.

## Exact source and pin

- Published base: `picomatch@4.0.7`, archive
  `https://registry.npmjs.org/picomatch/-/picomatch-4.0.7.tgz`.
- Base SHA-256: `697b463be3cdbd9ffc8f4194fd5019a69ddf95875fb703d78b2b115cc9e740a8`.
- Base npm integrity:
  `sha512-qcJu88Q2IWqJsDD529JKMdwGm/dvInW4HvQnRwiH9JtihJvzGOscDtHE3x1pBKeUOTysQ8kVmLnJ2kJu7yhcGA==`.
- `upstream-254.patch` is a zero-context diff of the PR's exact `lib/parse.js` security hunk. No other
  post-4.0.7 changes from its fork head are included.
- Patched archive SHA-256:
  `e0c1084e3580fab3440d420fbdf79ada687e74e01aa63a7076d61fdaed98843c`.
- Installed `lib/parse.js` SHA-256:
  `ccbcc9bb1333c4e03324fef8c729ea20979ef4f7b99d8f75c941abfec04b1cfd`.

The package retains its original name, version, license and all other published file
bytes. Only `lib/parse.js` changes. The MIT license remains in the archive.
The lockfile adds an integrity hash for the committed local archive; the package is
a direct dev dependency and all transitive uses are overridden through `$picomatch`.
No install/prepare/postinstall hook or network-dependent patch application is used.
The Docker build copies this same archive before its unchanged locked install.

Rebuild without network access after obtaining the original archive:

```sh
npm pack picomatch@4.0.7 --ignore-scripts --pack-destination /tmp
python3 scripts/build_picomatch_patch.py /tmp/picomatch-4.0.7.tgz --output /tmp/picomatch-rebuilt.tgz
cmp frontend/vendor/picomatch/picomatch-4.0.7-upstream-254.tgz /tmp/picomatch-rebuilt.tgz
```

The builder verifies the original archive, applies the exact reviewed hunk with zero
fuzz, checks other file bytes, and emits sorted tar entries with fixed metadata and
a zero-time gzip header. The committed archive, lock integrity and above hashes are
the installation pin. A different compression implementation may require comparing
the unpacked members before explaining a rebuild-byte discrepancy; never silently
replace the committed pin.

## Review and compatibility

The patch removes the redundant outer repetition only for a single branch whose
parsed tokens consist of ordinary stars and fixed-width text/question/bracket tokens.
Nested/alternative/path constructs retain existing handling. PR #238 instead
literalizes selected previously valid matches and does not cover the later-star
shapes as narrowly; PR #237 uses a larger separate character scanner. PR #254 is
the smallest reviewed candidate and operates on already-parsed tokens.

This is not a guarantee that all glob patterns are safe. The existing
`maxExtglobRecursion: false` opt-out remains intentionally unsafe and unchanged.
The patch's `capture: true` inner wildcard capture can span the flattened body
rather than only its last repetition; the outer match and tested boolean matching
are preserved. No explicit use of either option was found in Butler or its installed
Vite/Vitest/tinyglobby/fdir source. Broader API compatibility remains an upstream review risk.

**Additional observed compatibility regression:** a broader 825-comparison probe found
that `+([ab/]*)` matches `a/b`, `a/b/a`, `aba/` and `//` before this patch but rejects
them afterwards under the default, dot, Windows and capture options (16 differences).
A slash inside a bracket can cross the boundary the ordinary star cannot absorb;
the upstream single-branch closure assumption is therefore too broad for those shapes.
The installed-package check records the default `a/b` counterexample explicitly,
not as a preserved-semantic result. No local modification of the upstream hunk is
made to conceal this. The current Butler application tests pass, but that does not
establish that all consumer-generated patterns avoid the affected shape.
**This is an independent-review blocker for adopting the candidate**, alongside the
unchanged audit failure. Do not represent the bounded matching comparison as full
compatibility or the candidate as ready to merge.

`npm test` first runs `scripts/test-picomatch-patch.cjs`: archive/source pins,
consumer resolution, an isolated unpatched timeout control, an isolated patched
deadline, 42,966 short-input matching comparisons and explicit capture/opt-out checks.
It then runs the existing application tests. The unpatched baseline is reconstructed
only in a temporary directory and its source hash is checked before the timeout control.

## Audit remains authoritative

[GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf)
still lists 4.0.7 as affected and no patched release as of review.
The unchanged `npm audit --audit-level=high` still exits 1 with six high entries:
one source advisory and five dependent-package metavulnerability reports.
The package version is not relabelled to evade that range. This patch's regression
evidence does not resolve the advisory database finding or authorize merging red CI.
PR #54 is untouched and remains separately blocked.

## Removal and review plan

Remove the archive, override, direct dev pin, builder and patch-specific tests once an
official release is independently verified to fix these cases. Restore the ordinary
transitive dependency path, regenerate the lock narrowly, and require clean install,
regression/application tests, build, audit and container/browser evidence in that PR.
Do not auto-update the pin to a moving branch or another unreviewed commit.

## Validation and convergence

Local observed evidence and exact-head hosted CI are reported in PR metadata.
The original release suite plus the three upstream regression tests passed (1,986
tests) against the minimal patched release; the full fork suite passed (2,001 tests)
but includes unrelated upstream changes and is not the installed package.
Rebuilding the archive twice produced identical bytes. The installed dependency
graph resolves all four consumers to the reviewed package. Acceptance, operational,
gate/register statuses and Spec 074/075 remain unchanged.
