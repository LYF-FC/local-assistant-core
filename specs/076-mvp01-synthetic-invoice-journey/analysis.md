# Spec 076 pre-implementation analysis

Baseline `e088626331aff57d630d95faa721353a27bd468f` on `work/mvp01-invoice/a3-implementation`; `main` and that base were identical and no pull request was open when work started.

| Finding | Treatment |
|---|---|
| The browser has no filing request/status/history control although spec 069's routes exist. | Add controls over the existing exact-revision API; plan approval stays separate (R1, R2). |
| `filing_worker` CLI always builds the in-memory `SyntheticDestination`, so a restarted worker forgets effects and a keyed lookup would say "absent". | Opt-in durable ledger (R3); default unchanged. |
| `tests/restart_support.FileDestination` is test infrastructure. | Not reused as an adapter; the production-path module is separate and the test child gains a kind that constructs it. |
| Existing `test-ci-browser.sh` is Linux/CI-only and imports a CA into a runner NSS store. | Not made the Mac entry point; the Mac path exports the public CA for the owner's deliberate trust. Browser automation on this Mac needs a trusted CA or a container browser (see convergence). |
| Compose subnet `172.29.243.0/28` and Caddy `.2` are fixed in compose and the API proxy allowlist. | Single-stack: preflight refuses with the conflicting network named. On the author's Mac an unrelated development stack held the subnet, so the real `start` refused as designed. |
| Login is rate limited per account (5 / 15 min). | Documented; never cleared. The seeder and checker log in once each per run. |
| The simulated model cites the first line of its retrieved window. | The fixture question targets the total so the citation is the total line; documented as simulated. |
| Reminder worker loop is 30 s. | Documented as the expected delivery granularity. |
