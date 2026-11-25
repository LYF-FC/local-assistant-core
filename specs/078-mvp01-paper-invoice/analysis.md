# Analysis — spec 078 (consistency)

Base: `origin/main` `22420be8f9d7799e82aa8d38e88a1314dbc303d9`.

- **Decisions vs. design.** D4 asked for a browser view of the original; the brief required rendered page images with no active content. Client-side canvas rendering satisfies both without touching the backend or `pdf_worker`, at the price of one third-party browser dependency that is **unreviewed until A4 and the owner review it**. A server-side render would be stronger isolation but is a backend/worker change (rejected for this batch; a possible follow-up).
- **A-1..A-3 are recommendations, not owner decisions.** If A-1 becomes "detect a dropped line" the backend/UI grows and the effort leaves M; if A-2 becomes "assert live OCR text" the engine image must be pinned; if A-3 becomes "extra spec 052 states in the owner trial" new fixtures and steps are needed.
- **D7.** Each unavailable attempt adds a version. The UI guard only gates clicks; it cannot prevent an API client from adding versions.
- **Single stack (D9).** The new overlay adds an API dependency on a healthy `pdf_worker`; a stopped worker is re-applied after every `up`, so the API starts briefly with a healthy worker and then runs without it, as in the feasibility run.
- **Sign-ins.** Owner steps need at most three sign-ins; the agent checker used its own disposable stack.
- **Gaps stated, not hidden.** S14, S16, S18–S21 and the real-Mac browser pass are listed in the convergence record as not run or partly run.
