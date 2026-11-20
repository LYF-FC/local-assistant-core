# Picomatch research protocol — isolated and non-blocking

**Owner decision:** 20 November 2026, recorded in [DECISIONS.md](../DECISIONS.md#20-november-2026--run-isolated-picomatch-research-in-parallel-without-blocking-mvp-delivery).

## 1. Purpose and scheduling

Investigate whether a safe, maintainable and behavior-compatible resolution exists for the picomatch matching issue observed in Butler. The current dependency and behavior remain unchanged for MVP delivery. This research stream is separate from, and must never block or slow, the MVP critical path. The experimental frontend tooling replacement and temporary patch route remain deferred to the first minor release after an accepted MVP; no version or date is assigned.

PR #55's experimental patch was closed without merging because it rejected valid slash-class matches. Its historical diff and test evidence may be used as research input, not as an approved solution. The withdrawal of GHSA-fc5q-39xc-vjpf is not evidence that the observed matching behavior was fixed. Do not reopen PR #55 or infer that advisory status resolves compatibility or security concerns.

## 2. Isolation and prohibited actions

All work must occur in a separate disposable sandbox, worktree, branch or equivalent environment. It must not modify or interfere with:

- `main` or any active MVP branch;
- the active MVP working tree, release or delivery schedule;
- package manifests, lockfiles, installed dependency versions on MVP branches;
- audit thresholds, suppressions, workflow definitions, CI scope selection or required checks;
- production or deployed application state.

The research agent is not authorized to create or update a PR, push to an MVP branch, cherry-pick, merge, deploy, publish a package, change dependencies on an active branch, alter audit policy, waive a check or implement a candidate in the product. Do not make a production change. Do not run unbounded resource-intensive tests.

A research prototype or patch may exist only in the isolated environment and must be clearly labelled experimental. Any implementation or integration requires a separate explicit owner decision after review of the evidence.

## 3. Required investigation

1. Reconstruct the current behavior from the exact current repository revision and locked picomatch version. Identify the call sites, options, input constraints and expected matching semantics; do not assume the PR #55 test subset is complete.
2. Preserve a baseline compatibility corpus from existing tests and repository call-site behavior. Include the valid slash-class cases rejected by the PR #55 candidate and other relevant glob/extglob/brace/negation/escaping/separator cases actually supported by the application. Distinguish documented/used behavior from unsupported theoretical syntax.
3. Investigate candidate approaches: upstream-supported releases/fixes, narrowly scoped upstream patches, safe wrapper/normalization approaches, alternative implementations and configuration changes. Evaluate semantics at actual call sites, not in an isolated toy example only.
4. Test adversarial patterns and inputs for catastrophic or excessive backtracking / ReDoS. Include bounded timeouts, input-size limits and negative controls. Do not run uncontrolled worst-case patterns against shared or production resources.
5. Benchmark baseline and candidates with representative and adversarial workloads, reporting environment, versions, corpus, repetitions, warm-up, timing distribution, memory/resource observations and timeout behavior. Do not claim bounded performance from one timing sample.
6. Assess maintenance: upstream activity/support, provenance, patch size, license, transitive dependencies, compatibility surface, future update burden and whether the approach is supportable long term.

## 4. Acceptance criteria for a credible candidate

A candidate is reportable as viable only when evidence demonstrates all of the following:

- **Compatibility:** the complete relevant baseline corpus passes, including every valid behavior exposed as a regression by PR #55; no unexplained semantic regressions are accepted.
- **Security:** adversarial ReDoS testing demonstrates an acceptable bounded-risk profile under stated input and execution limits. Document residual risk; do not claim absolute proof of absence of ReDoS.
- **Performance:** representative workloads remain within explicit, justified budgets, and adversarial cases terminate within controlled limits. Compare like-for-like against the baseline.
- **Maintainability:** provenance and support are clear; the patch or alternative can be maintained without hidden forks, unexplained local behavior or weakening security/audit controls.
- **Reproducibility:** exact revisions, commands, test data/corpus identifiers and environment are recorded so another reviewer can reproduce the result.

A narrow reproduction passing, advisory withdrawal, a green CI result unrelated to the candidate, or a candidate that merely fixes one observed example is insufficient.

## 5. Deliverables and reporting

Provide a concise report containing:

- current baseline revision, package version, call-site inventory and behavioral assumptions;
- candidate approaches considered and why rejected alternatives fail;
- exact experimental patch/prototype and its isolated revision (if any);
- compatibility corpus, pass/fail results and regression analysis;
- adversarial test cases, timeouts, resource controls and observed results;
- performance methodology and comparative results;
- dependency/upstream provenance, maintenance assessment and licensing considerations;
- limitations, residual risks and a clear recommendation: viable candidate, more research required, or no viable candidate;
- explicit confirmation that no active MVP branch, dependency, lockfile, CI, audit policy or production state was changed.

Report immediately if credible evidence indicates a material security vulnerability affecting the currently deployed application. Otherwise, send a periodic concise status only if a real persistent/scheduled Claude environment is configured, or provide a report when a research session is explicitly run. Never imply that an ordinary Claude chat continues working after the session ends. If persistent execution is unavailable, state that limitation and stop at the end of the initiated session.

## 6. Stop conditions and authority

Stop and report if no candidate satisfies the acceptance criteria, if the work would require changing an active MVP dependency or CI policy, if resource use cannot be safely bounded, or if isolation cannot be guaranteed. Do not force a patch to meet a deadline.

A recommendation does not authorize implementation. Only a separate explicit owner decision may authorize a bounded implementation proposal. Even then, normal PR review, required CI, independent verification where applicable and owner acceptance remain in force. This protocol changes no MVP gate, requirement, dependency, CI rule, acceptance status or operational permission.
