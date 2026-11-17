# Temporary picomatch security patch

## Scope and authorization

On 17 November 2026 the owner authorized reviewing, testing and pinning the smallest
upstream fix in a separate draft PR, without hiding the advisory, bypassing npm audit,
changing statuses or merging. This package is development/build/test tooling only.
No application source, household data, provider or operational authorization changes.

The intended outcome is reproducibly installing picomatch 4.0.7 plus the single security
hunk and an explicitly local compatibility correction. The security hunk is from [upstream PR #254](https://github.com/micromatch/picomatch/pull/254),
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
- `compatibility.patch` is a separately labelled local correction, not an upstream
  commit. SHA-256: `b312df250bef52229939cafbc448205719f29435bc67c5b4d483a83b886b9af2`.
- Patched archive SHA-256:
  `30d3e22fdd64db323b10836c2e792ca1eb4febb4d2cd618f479155a9fa779543`.
- Installed `lib/parse.js` SHA-256:
  `6924cea42aff5a624d01f67991a5db661d9ca0678adc08453c2f2fcb053b8d38`.

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

The builder verifies the original archive, applies the two reviewed patches in order with zero
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

### Local compatibility correction

The upstream-only candidate incorrectly rejected `a/b`, `a/b/a`, `aba/` and `//`
for `+([ab/]*)` under default, dot, Windows and capture options. That historical
finding is retained here; the installed-package test reconstructs the exact former
candidate and requires all 16 counterexamples to fail there and pass after correction.

The correction is limited to a single bracket/star token pair, in either order.
Let S be the ordinary star's one-character alphabet, C the bracket's character
alphabet and W its optional literal bracket spelling. With U = S union C:

- `(B S*)+` becomes `B U* (W U*)*`.
- `(S* B)+` becomes `(U* W)* U* B`.
- For outer `*`, keep the existing optional group.

If W contains no character outside U, omit the W tail because U already absorbs it.
Otherwise each repeated W must cross a character excluded from U. This avoids
restoring the ambiguous outer repetition over an unrestricted star. Existing
leading guards and capture wrappers remain; bash stars and their dot-all flag are
handled according to the emitted wildcard rather than assuming a capture wrapper.
No parser-option fallback disables the security rewrite.

`npm test` first runs `scripts/test-picomatch-patch.cjs`: archive/source pins,
consumer resolution, two hash-verified original-release timeout sensitivity controls,
patched attack deadlines, 42,966 existing short-input comparisons and 302,616 new
bracket comparisons. The new cases include positive/negative brackets, literal
spelling, prefixes/suffixes, plus/star repetition, both token orders, Windows paths,
line endings, capture, bash and dot-all options. A separate two-second child-process
check covers 108 long failing bracket cases (10,000 characters or repeated bracket
words), in addition to the existing four attack shapes. It then runs application tests.

These are bounded boolean-matching and attack checks, not a proof of all glob
languages or capture-array compatibility. The documented upstream inner-capture
change and unsafe explicit opt-out remain. More complex token sequences continue
using the upstream hunk and need independent review; this local correction is not
claimed as a universal compatibility proof. The original baseline and upstream-only
candidate are reconstructed only in a removed temporary directory, with source
hash checks before use. The advisory/audit blocker remains unchanged.

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
tests) against the corrected minimal release, including upstream ESLint. The earlier
full fork suite passed (2,001 tests) on the upstream-only candidate; that historical
run includes unrelated changes and is not evidence for the corrected installed bytes.
Rebuilding the archive twice produced identical bytes. The installed dependency
graph resolves all four consumers to the reviewed package. Acceptance, operational,
gate/register statuses and Spec 074/075 remain unchanged.
