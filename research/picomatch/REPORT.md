# Picomatch isolated research report — EXPERIMENTAL, ADVISORY ONLY

Run date 20 November 2026. Research-only; no recommendation here is owner approval.

**Isolation statement.** All experiments ran in a throwaway scratch directory outside the repository (npm installs, patched package copies, a sandbox clone of the repo to read PR #55). This report, the harness and the unapplied patches are the *only* additions, committed as new files under `research/picomatch/` on the session's dedicated research branch `claude/picomatch-research-x5ijsb`. No MVP branch, `main`, `package.json`, lockfile, installed dependency, CI workflow, audit threshold/suppression, required check or production state was changed. No PR was created, and nothing was cherry-picked, merged, deployed or published. `git status` of the repository was clean before these files were added.

## Verdict

**NO VIABLE CANDIDATE FOUND** (more research would be needed to change that). No candidate meets the compatibility criterion, and no patch candidate meets the security criterion. Detail in §12.

## 1. Baseline

- Repo revision: `9c2d0a0933482b4adad396a515df186d0709401a` (main after PR #62, plus this branch).
- Locked version: `picomatch 4.0.7` (`frontend/package-lock.json`, `dev: true`), registry npmjs.org; archive SHA-256 `697b463be3cdbd9ffc8f4194fd5019a69ddf95875fb703d78b2b115cc9e740a8` (re-verified from a fresh `npm pack`).
- npm registry `latest` is still 4.0.7 (modified 2026-08-24).
- `npm ci --ignore-scripts && npm audit` on the unchanged lock in the sandbox: **0 vulnerabilities** (consistent with the 18 Nov withdrawal).
- Environment: Intel Xeon 2.10 GHz, 4 cores, 16 GB, Linux 6.18, Node v22.23.5, npm 10.9.9. (PR #55 evidence was macOS/arm64; this is an independent environment.)

## 2. Call-site inventory — important scoping finding

Butler's application source has **no direct picomatch usage** (no hits in `frontend/src`, `scripts`, or any `package.json` dependency list). Picomatch is a *transitive, dev-only* dependency of `vite`, `vitest`, `tinyglobby` and `fdir` (lock lines 1305, 1483, 1543, 1627, 971). The production image is `nginx` serving the static `dist/` built in a separate build stage (`frontend/Dockerfile`); picomatch is not in the runtime image.

Actual call sites (installed in the sandbox): `tinyglobby` calls `picomatch(pattern, options)` and `picomatch.scan(...)`; `vitest` calls `isMatch`/matchers; `vite` uses `tinyglobby`. Patterns are developer-controlled configuration, not user input. Patterns seen: vitest defaults `**/*.{test,spec}.?(c|m)[jt]s?(x)`, `**/*.{bench,benchmark}.?(c|m)[jt]s?(x)`, `**/node_modules/**`, `**/.git/**`, `**/{vitest,vite}.config.*`, and similar; the repo's own configs add none (`vite.config.ts` has no globs; `vitest run src` is a substring filter).

**Security consequence:** ReDoS needs an attacker-influenced *pattern*. I found no path by which untrusted input reaches a pattern in the deployed application. **No credible material vulnerability affecting the deployed application was found, so no immediate escalation is warranted.** Residual risk is limited to developer/CI machines processing a malicious pattern in a config or a dependency.

## 3. Expected matching semantics (baseline contract)

The compatibility contract used is **stock 4.0.7 behaviour**, plus hand-written expectations for call-site and slash-class cases. Slash-class semantics: inside an extglob, a bracket class that contains `/` (e.g. `[ab/]`) can consume a separator, and `*` cannot. So `+([ab/]*)` matches `a/b`, `a/b/a`, `aba/`, `//`, and also `a/c` (`[ab/]`=`a`, `*`=``; then `[ab/]`=`/`, `*`=`c`).

Findings about the baseline itself: picomatch never matches the empty string; a literal `.git` in a pattern matches a leading dot; a trailing `/` is optional. I wrote three wrong hand expectations at first (`**/.git/**` on `.git/config`, `+([ab/]*)` on `a/c`, `*([ab/]*)` on empty). I corrected them in `corpus.cjs` with inline `CORRECTED` comments after checking each against the language definition, rather than redefining the expectation to fit any candidate.

An independent polynomial-time reference matcher (`refMatch`) agrees with stock on most of the mini-grammar but not all (28,570 of 408,240 in-domain comparisons disagree, due to un-modelled picomatch rules for `**`, `?` at an extglob start, and `[^a]` vs `/`). It is therefore used only as a cross-check, **not** as ground truth. Stock remains the baseline.

## 4. PR #55 regression analysis (historical)

PR #55 (closed, head `b76461514b24f9de62f9de16c7922ae6b861579c`; archive SHA-256 `30d3e22f…9543` reproduced) = 4.0.7 + upstream PR #254 hunk + a local bracket/star "compat" patch.

- The upstream-only hunk (`pr254`) removes the outer repeat for single-branch wildcard bodies. That is language-preserving only if the body is closed under concatenation, which is false once a bracket class can consume `/` while `*` cannot. It therefore rejects `+([ab/]*)` on `a/b`, `a/b/a`, `aba/`, `//`.
- The local patch widens the star alphabet for one bracket/star pair, which fixes the 16 reported cases, but PR #55's own follow-up identified more witnesses (`+([ab/]*a)`/`aa/a`, etc.). **Reproduced here:** pr55 still rejects valid matches in G4 (6 cases), G6 (8,376 comparisons) and G7 (16,060 comparisons).

## 5. Candidates considered

| # | Candidate | Supported upstream? | Result |
|---|---|---|---|
| A | Official release/fix | npm `latest` = 4.0.7; upstream master `9fab7bf` has unreleased fixes but **still reproduces** the exponential case (`+(*a)` times out at n=30). No fix released | Not available |
| B1 | Upstream PR #254 (`c63a5bf`, open/unmerged, dated 2026-11-17) | No, unmerged | Fails compat and security |
| B2 | Upstream PR #237 (`1bf0d04`, references GHSA-fc5q-39xc-vjpf) | No, unmerged | Fails compat and security |
| B3 | Upstream PR #238 (`44f192`) | No, unmerged | Fails compat worst; regresses plain `+(*a)` on `a` |
| B4 | PR #55 (254 + local patch) | Local fork | Fails compat and security |
| C | Pattern lint/constrained-input wrapper | n/a | Not built; see below |
| D | Alternative engines `minimatch@10.2.6`, `zeptomatch` | Yes, other projects | Different semantics; not drop-in |
| E | Config: `maxExtglobRecursion` | Yes (4.0.7 option) | Does not fix |
| F | V8 linear-engine fallback flag | V8 flag | Does not fix; unsupported here |

- **C (wrapper).** Because patterns are static developer config, a lint that rejects ambiguous extglob shapes would pass trivially on actual patterns, but it fixes nothing in the library and changes semantics for rejected patterns. Not prototyped as it cannot be shown to be safe or complete (see ReDoS families below). Not viable as a product change.
- **D.** minimatch rejects 16 of 20 slash-class witnesses (`/` is a segment separator there) and has 1,252, 10,302, 136 and 10,944 comparison mismatches vs stock in G2/G3/G5/G6. zeptomatch also diverges (6/25 call-site cases, 13/16 slash-class witnesses). Neither exposes `picomatch.scan`, which `tinyglobby` calls, so replacing it needs a shim, i.e. a re-implementation. A real alternative would belong to the deferred toolchain replacement, not a matcher swap.
- **E.** `maxExtglobRecursion: 0/1/2` still times out on `+(*a)`, `+([ab/]*)!`, `+(*a|b)` at n=30. The option limits nesting depth only. `false` disables protection. The consumers do not pass it through anyway.
- **F.** The flag is `--enable-experimental-regexp-engine-on-excessive-backtracks`; it is not allowed in `NODE_OPTIONS`, and V8's linear engine does not support the lookaheads (`(?=.)`) in picomatch's output (`^(?:(?=.)(?:[^/]*?a)+)$`): `+(*a)` and `+(*a|b)` still time out with it.

## 6. Experimental prototypes

No new patch was written. The viable language-preserving fix would need a different regex construction (or state tracking), which PR #55's own investigation also concluded is outside a small patch. The patches in `patches/` are the unmodified upstream PR diffs (`git diff -U0 master PR -- lib/parse.js`; SHA-256: pr237 `6a7d8502…`, pr238 `5faacd93…`, pr254 `974987b0…`), applied to the 4.0.7 tarball with `patch --fuzz=0` for testing only. Nothing was installed anywhere.

## 7. Compatibility corpus and results

Harness: `harness/corpus.cjs`, `run.cjs`, `compare.cjs`; full table in `results/compare_table.txt`, `summary.json`. Each cell is a boolean `isMatch(input, pattern, opts)`; "mismatch" = differs from stock. Every mismatch was a **reject of a match stock accepts**; none was a false accept.

Groups: G1 call-site (25 + 3 dot:true, hand-expected); G2 PR55 "existing" re-creation (18 patterns × 7 options × 341 inputs = 42,966); G3 bracket (303,264); G4 slash-class witnesses (28, hand-expected, the 16 PR #55 regressions + 5 follow-up witnesses + controls); G5 glob/brace/extglob/negation/escape/posix/nocase families (14,391); G6 inside-extglob class/star shapes (139,904); G7 mini-grammar exhaustive over alphabet {a,b,/} up to length 6 (1,180,440).

Total 1,681,021 comparisons per variant (G1…G7 summed from the table).

| Variant | G1 | G4 | G2 | G3 | G5 | G6 | G7 | Mismatching comparisons / distinct patterns |
|---|---|---|---|---|---|---|---|---|
| stock | – | 0/28 | – | – | – | – | – | baseline |
| pr254 | 0 | **24** | 0 | 6,082 | 0 | 8,376 | 40,418 | 54,900 / 182 |
| pr237 | 0 | **24** | 0 | 6,082 | 0 | 8,376 | 35,602 | 50,084 / 174 |
| pr238 | 0 | 2 | 570 | 27,102 | 0 | 2,352 | 32,320 | 62,346 / 132 |
| pr55 | 0 | **6** | 0 | 0 | 0 | 8,376 | 16,060 | 24,442 / 98 |

Totals are comparisons from G2–G7 (the G1 counts are all zero). Note pr55 passes G2 and G3 (matching PR #55's own claim) and still fails G4/G6/G7. Examples: pr55 rejects `+([ab/]*a)`/`aa/a` and `+(a*[ab/])`/`a/aa`; pr238 rejects `+(*a)`/`a` and `+(*a)`/`aa`.

**Negative controls.** The harness detects the known regressions: PR #254 and PR #55 reproduce the exact historical failures; the corpus is therefore sensitive. **Call-site end-to-end:** real `vitest run src` through `tinyglobby` with each variant substituted: 33 files / 824 tests pass for stock, pr254, pr237, pr238 and pr55 — the actual toolchain usage is not affected by these regressions, but the criterion is the complete relevant corpus.

**Upstream test suite.** Upstream's own 4.0.7 `test/` (1,983 tests, mocha 10.8.2) passes on all five variants. It does **not** detect the slash-class regression, so a green upstream suite is not compatibility evidence.

## 8. Security testing (bounded)

Harness: `redos_driver.cjs` (`redos_child.cjs` per process). Each (variant, pattern, input family) runs in its own process with a hard 3 s wall-clock SIGKILL and `ulimit -v 2.5 GB`, 4 in parallel. Ladder n = 10, 14, 18, 22, 26, 30, 34, 40, 100, 1000, 10000, 50000 for non-matching inputs of three families (`a…a?`, `a/a/…?`, `abab…!`). 30 patterns × 3 families = 90 jobs per variant. Nothing was run against shared or production systems.

Sensitivity control: stock `+(*a)` n=14/18/22/26 → 3 / 13 / 161 / 2,197 ms and killed at n=30 (about ×2 per added character, i.e. exponential).

| Variant | Killed at 3 s (of 90) | Ladder fully completed |
|---|---|---|
| stock | 31 | 59 |
| pr254 | 11 | 79 |
| pr237 | 11 | 79 |
| pr238 | 17 | 73 |
| pr55 | 11 | 79 |

Candidates fix only the advisory's single-branch shapes. **Every patch candidate still times out** on: `+(*a|b)`, `+(*a|*b)`, `+(**)a`, `+({a,b}*)c` (brace expands to alternation). pr238 additionally still times out on `+(*)a`, `+([ab/]*)!` and `+([[:alpha:]]*)1`. Plain non-extglob `*a*a*a*a*a*a*a*a*b` also times out on **all** variants including stock (polynomial n^8, inherent to regex backtracking). The call-site patterns (13 distinct, stock and pr55): 0 of 78 jobs timed out, worst single measurement ≈ 2 ms up to 50,000-character inputs.

Limits: finite pattern/input set; a timeout ladder finds bad cases but cannot prove their absence; no fuzzing of pattern space beyond the hand-picked families; no claim of ReDoS safety for any variant.

## 9. Performance

`harness/bench_child.cjs`: 10 patterns (7 call-site/glob, 3 extglob) compiled once and matched against 1,500 synthetic paths with `dot:true` (15,000 matches per run); 5 warm-up runs, 30 timed runs, three independent processes per variant (nothing else deliberately loaded; 4-core VM). Median per run (ms), three rounds: stock 1.31 / 1.31 / 1.73; pr254 1.19 / 1.22 / 1.87; pr237 1.46 / 1.98 / 1.60; pr238 1.35 / 1.91 / 1.34; pr55 2.12 / 1.41 / 2.02. p95 ≤ 4.6 ms; RSS ≈ 50–52 MB; heap ≈ 6–7 MB for all. Round-to-round noise exceeds any between-variant difference, so there is no demonstrable performance regression and the benchmark does not discriminate. I set no performance budget because no candidate reached that stage meaningfully.

## 10. Upstream and maintenance

- Upstream `micromatch/picomatch`: MIT, no runtime dependencies for the base package; master is active (merged PRs through 2026-08-27 on unreleased master), last release 4.0.7. Three competing, unmerged security PRs (#237, #238, #254) exist for this issue and none has been accepted, which suggests the semantic trade-off (slash-class) is not trivially resolved even upstream.
- A local patch would be a permanent fork of `lib/parse.js` (PR #55: two patches + builder + vendored tarball + pinned hash; removal plan required). Acceptable only if the compat gap closed, which it has not.
- Any Butler-side fix should be an upstream contribution with a slash-class regression test; I did not post anything upstream.

## 11. Limitations

Differential testing treats stock as the contract (including any stock bugs). The reference oracle is partial. The corpus is bounded (≤6 characters in G7, ≤4 in G2); only booleans are compared, not capture arrays or `makeRe().source`. One platform/Node version. I did not verify the GitHub Advisory text itself (not retrievable here; web search found only GHSA-c2c7-rcm5-vvqj / GHSA-3v7f-55p6-f55p, which are different advisories already fixed in 4.0.4+). Upstream PR state is from git refs (no API access), so "unmerged/open" means unmerged as of the fetched `master` `9fab7bf`.

## 12. Recommendation

**NO VIABLE CANDIDATE FOUND** — keep picomatch 4.0.7 unchanged, as the owner decided.

- Compatibility: 0 of 4 patch candidates pass the complete corpus; the best (pr55) still rejects valid slash-class matches.
- Security: all patch candidates leave exploitable shapes (`+(*a|b)`, `+(**)a`, `+({a,b}*)c`), so even a compatible version would not be "ReDoS-safe".
- Performance: no difference detected.
- Maintainability: no official fix; local fork required.

Useful follow-ups if the owner wants more research: (1) a semantic, state-based extglob compiler or a non-backtracking matcher for the extglob subset, with this corpus as the acceptance test; (2) a upstream issue/PR contribution carrying G4/G6 as regression tests (owner decision needed before anything is posted); (3) re-run the harness when upstream releases > 4.0.7. Since patterns are developer-controlled and picomatch is dev-only, the practical risk is low and a no-change position is defensible.

## Persistence

This environment ran as an ordinary interactive session. I did not create a scheduled or background task, so **nothing continues after this session ends**. Re-run `harness/reproduce.sh` when asked.

## Reproduce

`bash research/picomatch/harness/reproduce.sh <empty scratch dir outside the repo>`. Commands, versions and hashes are in the sections above.
