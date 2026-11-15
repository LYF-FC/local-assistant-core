# Independent verification of spec 074 Phase B — process and blank record template

**Status: DRAFT. The independent-verification record is NOT complete, and nothing in this page claims that any criterion has passed.** It is an outstanding workstream and a prerequisite for any real-key or real-set use (spec 074 sections 11.6 and 11.7, step 3). This page proposes a process, names the exact revisions and evidence a future reviewer must verify, and provides a **blank** record. It does not copy forward any earlier sign-off draft: every result cell starts blank. The owner's formal acceptance of synthetic-only Phase B (15 November 2026), the hosted CI runs recorded in [RECOVERY_SET.md](RECOVERY_SET.md) and any earlier source review are not independent verification. It changes no gate, register row or status. Phase C design and preparatory work was authorized on 15 November 2026 and implementation of the non-operational portions later ([RECOVERY_PHASE_C_IMPLEMENTATION.md](RECOVERY_PHASE_C_IMPLEMENTATION.md)); this page is a blank template and nothing here is run, tested or executed.

## 1. Definition (spec 11.6)

Independent verification means a reviewer **other than the implementer** re-checking at an **exact `main` revision**, with **full rather than scope-reduced coverage**, and recording the result. It does not establish real key custody, real NAS/USB/network filesystem behaviour, clean-host recovery, RPO/RTO or owner acceptance.

## 2. Reviewer independence

- **Prior AI-assisted review does not automatically satisfy independence.** The pre-merge source review of PR #40 (recorded in `RECOVERY_SET.md`), and any reading of the code by an AI assistant that drafted or reconciled these documents, are not treated as independent verification.
- Whether an AI-assisted reviewer can count as independent of the implementer, and what independence means if the implementer or earlier reviewers were AI-assisted, is an **owner decision** (V2 below). Until it is made, no reviewer is assumed to qualify.
- The reviewer works from the repository at the chosen revision, not from the implementer's or any earlier reviewer's reports.

## 3. Exact revisions (candidates; the owner chooses, V1)

| Label | Revision | Facts (observed when drafting; the reviewer recomputes them) |
|---|---|---|
| R-A | `47b949e61c96a2e3c2fd883e1784a2856946146c` (merge of PR #40; parents `355fd6f` and `d5f8b0a`) | Hosted run 43647391844, attempt 3, ran and passed all six jobs at exactly this revision. Attempts 1 and 2 are not characterised. |
| R-B | `395d458b17d306f1aada20daf98d4f5cecdb4e85` (verified `main` when this page was drafted) | Documentation-only commits after R-A; the objects below are identical to R-A. Run 43652211367 passed only `scope` and aggregate `ci`; `backend`, `frontend`, `containers` and `postgres` were skipped. **No full-coverage run exists at R-B.** |

`main` may have advanced when the review starts; the reviewer re-reads `main`, records the revision actually reviewed and re-checks whether the objects below changed.

Git objects observed identical at R-A and R-B (a future reviewer verifies, for example with `git rev-parse <revision>:<path>`):

| Path | Object id |
|---|---|
| `backend/app/recovery_set` (tree) | `fb47e6501e4243df45283a8baa32a05d23761a40` |
| `backend/tests/recovery_set_support.py` (blob) | `5b88e07b75174f92c241179359beec993866b637` |
| `backend/tests/test_recovery_set_corrections.py` | `5f7e94c0e4d685f8cb91bdbe82064954ae19c099` |
| `backend/tests/test_recovery_set_format.py` | `855eed3a819abe0888c7d69c017b737a01b85880` |
| `backend/tests/test_recovery_set_fsset.py` | `9ce15f6917c860c840a8dfe7336639bcf4329267` |
| `backend/tests/test_recovery_set_publish.py` | `844e8576c171745b028a3fe3b6d69eb5249ef500` |
| `backend/tests/test_recovery_set_review.py` | `1079c63c55317fd2299afbd50c5c7d01366dec8e` |
| `backend/tests/test_recovery_set_verify.py` | `4c7918174ea1aecc3ede8760f77bca7282710fd5` |
| `scripts/test-db-restore.sh` (blob) | `e6d316d0f228c79e71ad0fb434931ad6c414d78e` |
| `.github/workflows` (tree) | `7f97ac7b1e680393dadcfc72d842b68255b5cc09` |

## 4. Evidence a future reviewer must verify

1. **Source against the frozen specification** ([spec 074](../specs/074-recovery-set-manifest/spec.md)): section 11.1 criteria A1 to A13 (including A7a and A7b), the test matrix T1 to T54 (section 11.2), the drill (section 11.3) and the limits of the evidence (section 11.8), each mapped by the reviewer to a source symbol, a test name and an observed result.
2. **The two owner-accepted interpretations** are implemented and tested as documented: only the first violation is reported under the closed section 7.3 output schema, with no count field and no repeated reason codes; and when temporary-link removal fails after publication but the directory fsync confirms durability the result is `published_durable` with `stale_temporary_present`, the resulting set remaining unverifiable until the temporary link is removed. The reviewer states whether the code and tests match this and whether any test contradicts it.
3. **Test evidence at the chosen revision with full coverage:** an existing full run at exactly that revision (available only for R-A) or a new full run (a manual workflow run requires full coverage by repository policy and **needs separate authorization; none is authorized here**). All six jobs must have run, none skipped; the PostgreSQL job's "Synthetic logical backup and isolated restore" step is among the evidence.
4. **Reviewer-run checks:** lint and format, security scan, the full non-integration and integration suites in CI shape, `scripts/check_repository.py` and `build_feature_overview.py --check`.
5. **Mutation checks** of plan section 1.4 re-performed by the reviewer on a scratch copy, each expected to make a test fail.
6. **Unchanged surfaces:** Work modules and tests unchanged from the pre-implementation baseline (`355fd6f`), no migration or alembic head change (A11, A12), and that the test-only limit-injection point is unreachable from the command line, environment and configuration (A13).
7. **What the record must say it does not establish:** real keys, real recovery sets, NAS or filesystem behaviour, clean-host recovery, RPO/RTO, owner acceptance.

## 5. Record template (blank; to be completed only by the reviewer)

| Field | Value |
|---|---|
| Revision actually reviewed | (blank) |
| Object ids recomputed for the paths in section 3 | (blank) |
| Reviewer, independence statement and owner determination under V2 | (blank) |
| Date | (blank) |
| Full-coverage run id, event, attempt and the six job results | (blank) |
| Local checks and results | (blank) |

| Criterion | Source symbol | Test name | Result at the reviewed revision | Reviewer notes |
|---|---|---|---|---|
| A1 Valid set | (blank) | (blank) | (blank) | (blank) |
| A2 Separation and state model | (blank) | (blank) | (blank) | (blank) |
| A3 Deterministic generation | (blank) | (blank) | (blank) | (blank) |
| A4 Closed set | (blank) | (blank) | (blank) | (blank) |
| A5 External trust inputs | (blank) | (blank) | (blank) | (blank) |
| A6 Freshness never overstates | (blank) | (blank) | (blank) | (blank) |
| A7 Atomic generation | (blank) | (blank) | (blank) | (blank) |
| A7a Informational notes | (blank) | (blank) | (blank) | (blank) |
| A7b Archive quiescence | (blank) | (blank) | (blank) | (blank) |
| A8 No secrets or foreign paths in output | (blank) | (blank) | (blank) | (blank) |
| A9 Point-in-time limitation | (blank) | (blank) | (blank) | (blank) |
| A10 No database, network or write to the set | (blank) | (blank) | (blank) | (blank) |
| A11 Work behaviour unchanged | (blank) | (blank) | (blank) | (blank) |
| A12 No migration | (blank) | (blank) | (blank) | (blank) |
| A13 Limits and provenance | (blank) | (blank) | (blank) | (blank) |

## 6. Owner decisions required (unresolved)

V1: the revision to verify (R-A, R-B or a later one). V2: whether an AI-assisted reviewer can count as independent, and under what conditions. V3: whether to reuse the existing full run at R-A or authorize a new manual full run. V4: who the reviewer is and where the record is kept.

## 7. Out of scope

Real keys, recovery sets, NAS or production access; synthetic-key runs; operational recovery; changing `spec.md`; any acceptance decision.
