# A5 Validation Design: Forwarded invoice, approved plan, explicit filing, durable synthetic destination, real restart

**Mode:** read-only. I changed no repo file, created no branch, commit or PR, ran no tests and started no stack. Commands run: `git rev-parse`, `git status`, `grep`, `sed`, and `git fetch --dry-run`, which fetched nothing. The GitHub tool was used once to read the latest commit on main.

**Evidence labels** (used on every important claim):
- **[EV]** EXISTING VERIFIED: I read the code or test and traced it.
- **[ENV]** EXISTING NOT INDEPENDENTLY VERIFIED: taken from a doc or another source.
- **[NBR]** NEW BEHAVIOR REQUIRED.
- **[PTA]** PROPOSED TEST ARCHITECTURE.
- **[GTC]** GUARANTEE THE TESTS CANNOT ESTABLISH.

---

## 1. Validation objectives and scope

**Objective.** Independently prove, with evidence not authored by A3, one owner-approved journey:
1. Sign in.
2. Import a synthetic `.eml` with one invoice attachment.
3. Re-import it and see replay handling.
4. Review the invoice fields and source provenance.
5. Prepare and approve a logical filing plan.
6. Request filing through the UI with all acknowledgements.
7. Watch the pending and terminal status.
8. Verify a durable synthetic destination effect and its checksum.
9. Stop and restart the real worker and application, and verify the outcome is unchanged.
10. Exercise the replay, permission, stale-revision, failure and inconclusive-outcome protections.

**In scope.** The filing path: `filing.request`, the worker, the destination adapter, the DB guards, the audit and history, the UI and the container stack.

**Out of scope.** Agenda, document answer and reminder are not silently added. No real filesystem, NAS, mailbox or provider is touched. Owner acceptance is not claimed.

**The central finding.** The backend is largely built and unusually well tested, but the journey is not achievable today. Four things are missing:
1. A UI caller for filing request.
2. A UI view of status.
3. A worker in the container stack.
4. A destination that survives a worker or application restart inside that stack.

All four are **[NBR]**. Detail follows in section 3.

## 2. Repository baseline and exact SHA

- Local HEAD is `d990ae2e73a3118e79745c853d3e9c7ce71d071e` ("docs: add Butler agent orchestration charter"). **[EV]** The working tree is clean. The latest commit on GitHub is the same SHA, read via the GitHub list-commits tool on 2026-11-21.
- **[EV]** `PROJECT_MASTER.md` line 90 and line 146 onward record Gate 7 (MVP-03) as "Subset (synthetic destination, in-process)... Tested (in-process; process-restart, synthetic destination)... Not verified... Not accepted". 0 of 11 gates are accepted. Nothing in this report changes that.
- **[EV]** `docs/project-orchestration/instructions.md` defines A5 (§2) as validating the delivered journey and separate from the implementer. The batch lifecycle (§4) places A5 design at step 4, before implementation. A5 verification at step 7 is not owner acceptance at step 8.

## 3. Relevant implementation and spec findings

### 3.1 Prior leads from BMJI: verified or refuted

| Lead | Verdict |
|---|---|
| No frontend caller of `POST /api/v1/filing/request` | **[EV] Confirmed.** `grep` finds no `filing/request` in `frontend/`. Only `/api/v1/filing/query` is used, by `attention-api.ts` for the failed and unknown lists. `FilingPlanPanel.tsx` (16 lines) ends at "Approve filing plan only". `docs/FILING_EXECUTION.md` says "No web screen is added". Spec 069 `spec.md` ~line 57 lists "a web screen for filing" and "durable synthetic ledger across restarts" as out of scope. The owner-approved batch now overrides that exclusion, so the spec and master need an owner-authorised amendment (see section 14). |
| `inbox.spec.ts` asserts no filing request call | **[EV] Confirmed.** `frontend/e2e/inbox.spec.ts` lines 8, 45, 65-66 and 88 allow only POSTs to the `READ` set and fail on any other mutating request. Note: this is the inbox view, not the plan panel. If the new UI sits in the document view, this spec is unaffected. If it touches the inbox, line 65-66's `/file/` regex needs care. |
| `filing_worker` not in default compose | **[EV] Confirmed.** `infra/core/compose.yml` defines only `postgres, migrate, api, web, caddy, role_setup, reminder_worker, routine_worker, calendar_worker`, the last three behind profiles. There is no `filing_worker` in any `infra/core/*.override.yml` (grep). `OPERATIONS.md` line 98 says "optional development/test engineering... not started by default". |
| Worker uses a destination that writes nothing | **[EV] Confirmed.** `backend/app/filing_worker.py` `main()` lines 276-299 build `filing.SyntheticDestination()`, an in-memory dict (`backend/app/filing.py` lines 46-82). It requires `settings.env in {"development","test"}` and `postgres_user == "butler_runtime"`. In test it also requires a DB name starting with `butler_test`. Its ledger is empty after any process restart, so a lookup would answer "absent". |
| `restart_worker.py` plus `FileDestination` plus SIGKILL tests exist | **[EV] Confirmed.** `backend/tests/restart_support.py` has `Ledger` (lines 34-111), which publishes exclusively via `os.link` and fsyncs append-only logs. `FileDestination` is at lines 118-152, `Worker` at 182-271 and `restart_worker.py` is the child entry. `backend/tests/integration/test_filing_restart_postgres.py` has 12 tests (lines 91-340). These run in the CI `postgres` job via `pytest -m integration`. Limits: the API is an in-process FastAPI TestClient, the ledger lives in pytest `tmp_path`, and there is no container, no app restart, no browser and no UI. Time is compressed by backdating rows with the trigger disabled (`age()`/`due()` in `test_filing_fence_postgres.py` lines 29-55). |
| `scripts/test-containers.sh` has no service restart | **[EV] Confirmed.** `grep restart\|stop\|kill\|pause` over `test-containers.sh`, `test-ci-browser.sh` and `test-db-restore.sh` finds nothing that restarts a service. The only teardown between phases is `compose down --volumes --remove-orphans`, which destroys data rather than testing durability. Line 138 does run six specs in one phase: `answers.spec.ts calendars.spec.ts routines.spec.ts invoices.spec.ts emails.spec.ts installation.spec.ts`. |
| `test_mvp03_journey_postgres.py` exists | **[EV]** It has 7 tests. It drives the real HTTP routes in-process and the worker with the in-memory destination. Its module docstring explicitly says it does not prove survival across a process restart. |
| Env-gated browser specs | **[EV]** `invoices.spec.ts` line 2 and `emails.spec.ts` line 3 skip unless `BUTLER_INVOICE_BROWSER_TESTS`/`BUTLER_EMAIL_BROWSER_TESTS` is `1`. `scripts/test-containers.sh` line 138 sets both, so CI does run them. |

### 3.2 How `filing.request` ties to approvals and acknowledgements

All **[EV]** from `backend/app/filing.py` lines 127-136 and 269-354.

- **It is not the generic approvals table.** `filing.py` imports no approvals module. The "approval" is the invoice plan's `approved` state, plus a separate exact action authorization created by `POST /api/v1/filing/request`.
- **Request body** (`Request`): `scope`, `document_id`, `expected_document_revision` (strict int, ≥1), `expected_review_revision` (strict int, ≥1), and `acknowledge_synthetic_destination` and `acknowledge_exact_plan`. Both acknowledgements are `Literal[True]` and are validated in `before` mode by `explicit()`. `1`, `"true"` or missing returns 422 at the request-model layer. `extra="forbid"`.
- **Handler order:**
  1. `authority()` (`manual_tasks.py` lines 81-126): token length 40-128, session lookup, user row `FOR UPDATE` (exclusive), active user, `identity.resolve`, CSRF via `hmac.compare_digest`, then `butler_lock_task_scope(actor, scope)`. Failures are 401 `filing.session_denied`, 403 `filing.csrf_denied` or 403 `filing.scope_denied`.
  2. Source `FOR UPDATE` with `documents.visible`. 401 if the session was revoked meanwhile, 404 `filing.not_found`, 403 `filing.owner_denied` if the caller is not the owner.
  3. Review row `FOR UPDATE`. 409 `filing.source_changed` if the document revision differs, and 409 `filing.review_changed` if the review revision differs.
  4. `current_plan()` requires source active, review `reviewed`, plan `approved`, `approved_revision == review.revision`, matching source revision and sha256, and eligible source. Otherwise 409 `filing.plan_not_approved`.
  5. If an execution already exists for `(document_id, plan_revision)`, return 200 `{"replayed": true, "filing": ...}` with audit `filing.replayed`. This holds even if that execution is `failed` or `cancelled`. `uq_filing_dedup` enforces one per pair.
  6. `destination_key(scope, relative_path)`. 422 `filing.invalid_destination` if invalid. 409 `filing.destination_taken` if an active execution (pending, unknown or filed) holds the same key.
  7. Insert `pending` (revision 1) with a `requested` event and audit `filing.requested`. The insert is in `begin_nested` and an `IntegrityError` returns 409 `filing.destination_taken`.
- **Single use.** `authorization_consumed_at` is set by the first claim, in the same update that increments `attempts` (`filing_worker.claim()` lines 133-143). The DB check constraint `ck_filing_consumed` and the seal trigger enforce it. A re-request after cancel, failure or success returns the existing row, so retry after a collision needs a new plan revision.
- **Plan approval never authorizes.** `execution_authorized: false` is permanent, and the frontend parser in `invoices-api.ts` line 24 rejects anything else. This must remain true. The new UI control must be separate from "Approve filing plan only", and `FilingPlanPanel`'s copy ("cannot authorize a future worker") stays accurate.
- **Audit and history.** `record_event` (`filing.py` lines 183-230) writes `filing.<operation>` with metadata `{revision, state, attempts, reason}` only. The worker's events use `initiator_type="system"`, `initiator_id="filing_worker"`. No path, filename or invoice field appears in audit or history. Responses from `view()` carry no path or checksum.

### 3.3 The destination interface (what any durable destination must satisfy)

All **[EV]** from `filing.py` lines 33-82 and `filing_worker.py` lines 222-241.

- `put(key, path, sha256, size) -> Outcome` where `Outcome` is `ACCEPTED`, `COLLISION`, `TRANSIENT` or `TIMEOUT`. `key = str(filing_execution.id)` and `path` is the canonical, lower-cased logical path.
- `lookup(key) -> Lookup` where `Lookup` is `FILED`, `ABSENT` or `UNAVAILABLE`.
- Any exception from `put` is treated as `TIMEOUT` (ambiguous). Any exception from `lookup` is treated as `UNAVAILABLE`.
- Semantics:
  - The same key and the same path returns `ACCEPTED` (idempotent).
  - A different key on the same canonical path returns `COLLISION`.
  - `TIMEOUT` moves the row to `unknown`.
  - `COLLISION` moves it to `failed`.
  - `TRANSIENT` schedules a retry with backoff 1/5/15 minutes, up to 3 attempts, then `failed` with `attempts_exhausted`.
- **No bytes cross the interface.** `put` receives only the DB's `source.sha256` and `byte_size`. `docs/FILING_EXECUTION.md` states "the original bytes are not copied". "Verify checksum" therefore means the destination entry's recorded sha256 equals the independently computed attachment sha256. It does not mean file contents were verified. A mismatch is not detected by the worker, because `lookup` returns only found or absent. **[GTC]** The system cannot establish that a stored artefact equals the original bytes unless an owner-approved **[NBR]** passes bytes. This is open question Q1.
- Timing constants (`backend/app/notifications.py` lines 17-20): `MAX_ATTEMPTS=3`, `BACKOFF=(1m,5m,15m)`, `IN_FLIGHT_DEADLINE=5m`, `RECONCILE_INTERVAL=1m`. `filing_worker.main()` sleeps 30 s per pass, hard-coded at line 299. A real-time crash recovery is therefore about 5 min (reap) + 1 min (reconcile) plus up to 60 s of pass jitter. `docs/FILING_EXECUTION.md` also says a real adapter needs a hard write timeout below the 5-minute in-flight deadline.

### 3.4 Worker and DB guards

- **[EV]** `claim()` takes locks in the order owner, source, review, filing row, then re-checks the plan, owner active, scope grant and destination key. A mismatch cancels with `plan_changed`, `owner_unavailable` or `scope_unavailable` and no effect.
- **[EV]** The claim commits before the effect (`process()` lines 223-232). A stale worker is fenced by `WHERE revision = :fence FOR UPDATE`.
- **[EV]** The seal triggers are `butler_seal_filing` and `butler_seal_filing_event`, with truncate triggers (`0034_invoice_filing_execution.py` lines 69-226). They enforce an approved plan on insert, a pending start, sealed identity, destination and revision, a claim before any terminal outcome, and append-only history. I read the `RAISE` messages by grep only, not each trigger body.
- **[EV]** `runtime_role.py` lines 139-163 grant `butler_runtime` `SELECT, INSERT, UPDATE` on `filing_executions` and `SELECT, INSERT` plus `UPDATE (snapshot)` on `filing_execution_events`. There is no `DELETE`.
- **[EV]** `scrub_for_document` (`filing.py` lines 387-425) cancels unfinished filings and nulls snapshots and keys. A destination effect that already happened cannot be recalled. This is documented.
- **[EV]** The destination is not scope-qualified. `SyntheticDestination.put` collides on the canonical path alone, while the DB `destination_key` is scope-qualified. Two scopes with the same manual path pass the DB reservation, and the second would fail at the destination with `collision`. No test for this was found in the files I read (test names only).

### 3.5 Email intake, replay and provenance

All **[EV]** from `backend/app/email_intake.py` lines 76-140.

- **Intake and replay.** `POST /api/v1/email-intake`: the message is decoded from base64, then `message_sha256` is computed and matched per `(owner, scope, message_sha256)`.
  - A replay returns 200 `status:"replayed"` with the same document and audits `email_intake.replayed`.
  - A forgotten message returns 410.
  - A quota above 4 MiB returns 409.
  - An unsupported structure returns 422.
- **Attachment checksum.** `EmailEnvelope.attachment_sha256 = source.sha256`, so the document's `sha256` is the attachment's sha256. `message_sha256` is the whole `.eml`.
- **MIME parser limits** (`email_mime.py`): root must be `multipart/mixed` with `MIME-Version: 1.0`. The boundary must match `[A-Za-z0-9_=.-]{1,70}`. There must be 1-2 parts with exactly one attachment, `Content-Transfer-Encoding: base64`, and a strict content-type match (`application/pdf` for `.pdf`, otherwise `text/plain`). No duplicate singular headers are allowed. Documents accept `.txt`, `.md` and `.pdf`.

### 3.6 Existing browser coverage for steps 1-5

- **[EV]** `frontend/e2e/emails.spec.ts` (test 1) covers login as `browser-email-flow`, import, provenance ("matches current bytes"), download equal to the raw bytes, review, "Suggest filing plan" reaching "Plan status: proposed", replay ("Exact email already imported", which keeps the original title), forget, and 410 on a forgotten replay. It stops at "proposed" and never approves.
- **[EV]** `frontend/e2e/invoices.spec.ts` test 3 covers suggest, approve (two checkboxes), "Plan status: approved", the history showing `"execution_authorized": false`, withdraw, manual plan and plan clearing on re-review.
- **[EV]** Users are seeded by `scripts/browser-fixtures.py` through the privileged `migrate` container. `browser-email-flow` and `browser-invoices-flow` hold `household_shared` and `member_a_private`. The password is a synthetic constant. The script guards on `settings.env=="test"` and `postgres_db=="butler_test_container"`.
- **[EV]** The emails spec fixture is a hand-built CRLF multipart with boundary `synthetic-browser-058` and a `synthetic-email.txt` attachment (5 lines of labelled fields).
- **[ENV]** The existing PDF path is not needed here. I did not read the PDF extraction pipeline, so a `.pdf` attachment is not recommended for this batch. See Q5.

### 3.7 Existing filing test coverage (names read; bodies read only where cited)

- `backend/tests/test_filing.py` has 33 tests on SQLite, including: acknowledgements and revisions (123), unapproved or withdrawn plan (132), owner-only and cross-user query and history (143), ambiguous timeout (159), unavailable lookup (182), destination exception (198), transient retry and exhaustion (211), no overwrite (229), plan withdrawn cancels (242), cancel rules (254, 281), forgetting (294, 307, 516, 551), authorization consumption (420, 444, 465) and a stale worker (657).
- `backend/tests/integration/test_filing_postgres.py` has 31 tests: runtime least privilege (309), raw seal guards (248-285), insert guards (352-437), forgetting races (454-1030) and concurrency (112, 557, 1030).
- `test_filing_fence_postgres.py` has 9 tests.
- `test_filing_downgrade_postgres.py` has 1 test.
- `test_filing_restart_postgres.py` has 12 tests.
- `test_mvp03_journey_postgres.py` has 7 tests.
- **Gaps** I could not find in the filing test names or the lines I grepped:
  - CSRF-missing on filing request.
  - An expired or revoked session on filing request. The leakage suite lists filing request, cancel, query and history among 13 "uncovered limitations" (`PROJECT_MASTER.md` line 111).
  - A grant revoked between request and claim (`scope_unavailable`) through a real worker.
  - A concurrent request from two sessions of the same user.
  - A UI test of any kind.
  - A test that audit rows contain no path or content, apart from the metadata-only check in `test_filing.py` line 90 (I read only its name).

### 3.8 CI facts

- **[EV]** `.github/workflows/ci.yml` has jobs `scope`, `backend`, `frontend`, `postgres`, `containers` and `ci`. The `containers` job has `timeout-minutes: 25`.
- **[EV]** The `postgres` job runs `pytest -m integration` against a `postgres:17` service as user `postgres`. It also runs `scripts/test-db-restore.sh`.
- **[EV]** `scripts/ci_scope.py` has `JOBS = ("backend","frontend","postgres","containers")`. Backend, schema or infra changes run all jobs, and frontend-only changes run `frontend` and `containers`.
- **[ENV]** I did not read `scripts/ci_gate.py` or `.github/workflows/release-candidate.yml`.

## 4. Durable synthetic destination architecture recommendation

### 4.1 Options compared

| Option | Persists independent of worker | Isolated per run and disposable | Confusable with a real filesystem or NAS | Network and real-fs effects | Failure injection and inconclusive lookup | Independently observable after restart | What it proves | What it does NOT prove |
|---|---|---|---|---|---|---|---|---|
| **A. In-DB table (same DB, same role)** | Only as long as Postgres | Yes (same DB) | No | None | Weak (SQL only) | Only through the same DB | Nothing about an external effect. It shares fate and role with the filing row. | Cross-store reconciliation. The "after effect, before record" window is no longer a distinct store. **Reject.** |
| **B. Separate Postgres schema, different role, same DB** | Yes | Moderate: `down -v` removes both stores | Low | None | Medium | Via a second credential | An independent commit and role, so two transactions. | A truly separate failure domain. Same cluster, same volume, same backup. No network timeout semantics. |
| **C. Separate Postgres database or cluster container** | Yes | Good | Low | Network to an internal host | Medium | Yes | A distinct failure domain. | Heavy, and still a SQL surface rather than a destination contract. |
| **D. Sidecar container, own volume, tiny HTTP ledger API, internal network** | Yes, independent of both worker and app, and also of Postgres | Good: own named volume, removed by `down -v`, per-run id | Very low, because entries are keyed JSON records, not a folder tree | Real network hop on an `internal: true` network. No egress. | Strong: real timeouts, real "held" requests, stoppable | Yes, through its own read-only viewer, independent of the app | A real cross-process, cross-container, cross-restart destination with real timeout semantics and an independent observer | A real NAS, a real filesystem driver, the permissions of a real mount, or content integrity (no bytes are sent) |
| **E. Shared volume or tmpfs ledger file mounted into the worker** | Volume yes, tmpfs no | Moderate | Higher: the worker gets a writable filesystem mount | No network | Medium (flag files) | Via the shared mount | Persistence only | Network failure semantics, and it gives the worker a filesystem write path, which is the opposite of the isolation wanted. |
| **F. Existing `FileDestination` plus `restart_worker` harness (pytest subprocess)** | Yes (pytest `tmp_path`) | Yes | Low | None | Excellent: exact hooks `before_effect`, `after_effect`, SIGKILL | Via `Ledger` readers in-test | Precise crash windows against real OS processes | Real containers, a real application restart, a browser, a real network, restarts of Postgres or the sidecar |

### 4.2 Recommendation **[PTA]**

**Use D for the container and browser layers, and keep F for precise crash-window coverage.** The two are complementary and share one design: exclusive-create entries, an fsynced append-only call log, and a lookup that distinguishes found, absent and unavailable. Do not use A, B or E for this journey.

### 4.3 Design of D

1. **Service.** `synthetic_filing_destination` is defined only in a new override file, for example `infra/core/filing-synthetic.override.yml`. The base `compose.yml` never references it. This follows the existing precedent of `answers-synthetic.override.yml`, whose `synthetic_answer_model` sidecar runs a mounted script in the backend image.
2. **Network.** Put the sidecar and `filing_worker` on a new `destination` network declared `internal: true` (as `edge`, `app` and `data` are). The API and Caddy do not join it, so the API cannot reach the destination. That keeps the API's authority and the destination's independence distinct. The owner viewer is published on `127.0.0.1` only, read-only, only in the owner override. It is not reachable from the data network.
3. **Storage.** One named volume `synthetic_destination_data` mounted at `/ledger`. No bind mounts, ever. The root filesystem is `read_only: true`. Also `cap_drop: [ALL]`, `no-new-privileges`, and `pids_limit` and `mem_limit` as the existing services have. `compose down --volumes` removes it. The volume holds only JSON records, never invoice content.
4. **Ledger format.** Reuse the reviewed `restart_support.Ledger` pattern:
   - `objects/<sha256(canonical_path)[:40]>` is created exclusively with temp-file, fsync and `os.link`.
   - `calls.log`, `effects.log` and `lookups.log` are append-only with fsync.
   - A marker file `SYNTHETIC-DESTINATION-NOT-A-STORAGE-LOCATION` and a per-run `run_id` file.
   - An entry is `{key, path, sha256, size, run_id}`. Content is never stored. A record is not a file at a folder path, so it cannot be mistaken for a NAS tree.
5. **HTTP API (stdlib server).**
   - `GET /v1/identity` returns `{kind:"butler-synthetic-filing-ledger", run_id}`.
   - `PUT /v1/entries/{key}` with `{path, sha256, size}` returns 201 (created), 200 (same key and path, idempotent) or 409 (a different key owns the path).
   - `GET /v1/entries/by-key/{key}` returns 200 `{found:true,...}` or 200 `{found:false, ledger_id}`.
   - **Mapping in the adapter:** a 200 or 201 maps to `ACCEPTED` and a 409 to `COLLISION`. A connection error or read timeout after the request may have been sent, or any unexpected status, maps to `TIMEOUT`. Only a definitive "refused before effect" (a typed 503 body) maps to `TRANSIENT`. For lookup, only a 200 with `found:false` **and** the expected `ledger_id` maps to `ABSENT`. Anything else, including a bare 404 or a misrouted reply, is `UNAVAILABLE`. This stops a wrong host or a proxy from fabricating "absent", which would trigger a re-write. The adapter must set a hard HTTP timeout below `IN_FLIGHT_DEADLINE`.
6. **Fault injection (the control plane is not on the network).** Use `docker compose exec synthetic_filing_destination python -m ctl <mode>`. This writes a control file inside the sidecar volume, as `Ledger.block_lookup()` does. Modes:
   - `hold-before-effect`: receive the PUT and block before writing.
   - `hold-after-effect`: write the entry, then block before replying. This is the "effect applied, worker dies before recording" window.
   - `transient-once` and `transient-n`.
   - `timeout-applied` and `timeout-lost`.
   - `lookup-unavailable` and `lookup-error`.
   - `preseed-collision <path>`.
   - `status` reports `held=true/false` so a test can synchronise on events rather than sleeps.
   - There is no secret for the worker to learn, and nothing on the network can switch a mode.
7. **Safety guards in the worker entry (new product code, test and dev only).** Select the destination with `BUTLER_FILING_DESTINATION=synthetic-ledger` plus `BUTLER_FILING_DESTINATION_URL`. Refuse to start unless all of these hold:
   - The existing guard holds: env in {development, test}, role `butler_runtime`, and in test the DB name starts with `butler_test`.
   - The URL host is exactly the literal compose service name, with no IP and no public suffix.
   - `GET /v1/identity` returns the expected `kind` and a `run_id` equal to `BUTLER_SYNTHETIC_RUN_ID`.
   - Refuse before any `put`, not after.
   - `staging` and `production` are already refused by the existing env check. That is the property that makes this inaccessible to prod and staging.

### 4.4 What D proves and does not prove

**Proves:**
- Effect durability independent of the worker, the app and Postgres lifetimes.
- A real network hop with real ambiguity (timeout after apply).
- Reconcile by key against an independent store.
- No duplicate effect across restart.
- Independent observability of the effect and its checksum.

**Does not prove, and the report must say so:**
- **[GTC]** The behaviour of a real NAS or filesystem: permissions, partial writes, case-folding, capacity, symlinks, atomic rename.
- **[GTC]** Bytes were stored or are intact. Only the sha256 and size the DB asserted are recorded. A destination holding wrong bytes would not be detected.
- **[GTC]** Cross-store atomicity. The DB commit and the effect are never one transaction. The design handles that through claim-then-effect-then-reconcile, and D shows that holds against a real separate process, but it is still synthetic.
- **[GTC]** Anything about real providers, authentication to a real destination, or real credentials.

Option A would show only a DB row consistent with itself, which proves nothing about reconciliation. Option B shares a failure domain with the filing row.

## 5. Test scenario matrix

Layer codes: **U** = unit and API (SQLite, `test_filing.py` style), **P** = restricted PostgreSQL, **PS** = PostgreSQL plus SIGKILL subprocess harness (`test_filing_restart_postgres.py` style), **C** = container real-process restart, **B** = browser E2E, **O** = owner manual.

Common fixture for all: a disposable stack (project name and DB distinct per run), users seeded via the privileged `migrate` container, and the deterministic `.eml` of section 9.1.

### 5.1 Happy path and replay

| ID | Initial state / fixture | Exact trigger | Expected API / UI | Expected DB + audit | Expected destination | After restart | Pass / fail assertion | Layers, label |
|---|---|---|---|---|---|---|---|---|
| **H1** import | Fresh stack, user `e2e-owner` with `member_a_private`, empty destination | Browser: sign in, open Documents, scope `member_a_private`, "Import forwarded email…", title, file, "Import email attachment" | 201. Region "Offline email import" says "Attachment imported unreviewed". The document is selectable. | One `document_records` row with `sha256 == attachment sha256`. One `email_envelopes` row with `message_sha256 == published message sha256`. Audit `email_intake.*` with only `document_revision`. | Untouched (0 entries) | Same row after restart | `document.sha256 == published ATTACHMENT_SHA256`. `envelope.message_sha256 == published MESSAGE_SHA256`. `original_message` bytes equal the fixture. Destination has 0 entries. | B, O: **[EV]** for the import and replay path (`emails.spec.ts`, `test_mvp03_journey...:forwarded`). |
| **H2** replay | After H1 | Import the same bytes again with a different title | 200 `status:"replayed"`. The UI says "Exact email already imported". The title is not renamed. | Still one envelope and one document. Audit `email_intake.replayed`. | Untouched | Replay still returns 200 after the stack restart | Count of documents and envelopes for that message sha is 1. Title unchanged. | B, P: **[EV]** |
| **H3** review and provenance | After H1 | "Load original email provenance", then "Correct and review", tick the checkbox, "Save document", "Load invoice review", "Prepare invoice candidates", "Use Issuer/Invoice number/Issue date/Total/Currency candidate at line 1-5", tick the attestation, "Save invoice field review" | UI shows "matches current bytes". The downloaded `.eml` equals the fixture. | An `invoice_reviews` row in `reviewed` state, revision recorded. | Untouched | Review still readable | Candidate values equal the fixture's published fields. Downloaded bytes' sha256 equals `MESSAGE_SHA256`. | B: **[EV]** (`emails.spec.ts` test 1) |
| **H4** plan approved | After H3 | "Suggest filing plan", then tick both approval boxes, "Approve filing plan only" | "Plan status: approved". "No file has been written". | Plan `approved`, `execution_authorized:false`, `approved_revision == review.revision`. No `filing_executions` row. | Untouched | Plan still `approved` | Zero filing rows after approval. History shows `"execution_authorized": false`. | B: **[EV]** (`invoices.spec.ts` test 3) |
| **H5** explicit request | After H4, worker **stopped** | Click the new "Request filing" control, tick both new acknowledgements, press the new button | **[NBR]** 201. The UI shows status `pending` and an explicit statement that the destination is synthetic. | One `filing_executions` row: `pending`, `revision=1`, `attempts=0`, `authorization_consumed_at NULL`. `filing_execution_events` revision 1 `requested`. Audit `filing.requested` with `{revision, state, attempts, reason}` only. | Still 0 entries (worker stopped) | If the stack is restarted now, the row stays `pending`, the plan stays `approved`, destination stays empty | The button is disabled until both boxes are ticked. Exactly one row. Destination empty. The UI shows pending after reload. | B, P, C: **[NBR]** UI. **[EV]** API (`test_filing.py:68`, `test_mvp03...:journey_to_request`). |
| **H6** execute | After H5, start worker | `compose up -d filing_worker` | UI status moves `pending` to `filed` on a poll or refresh. | `attempts=1`, `authorization_consumed_at` set, `state=filed`, `resolved_at` set. Events `["requested","attempted","filed"]`. System audit `filing.attempted`, `filing.filed`. | **Exactly one entry** keyed by the execution id, with `sha256 == ATTACHMENT_SHA256` and `size == ATTACHMENT_BYTES`. | See section 6 R1 | Independent read of the sidecar viewer: one entry, key equals the API's execution id, checksum equals the **published** value (not the DB's). Calls log has 1 PUT. Plan path in the ledger equals the plan's canonical path. | B, C, O: **[NBR]** end to end. **[EV]** for the worker semantics (`test_filing_postgres.py:112`, `test_filing_restart_postgres.py:203`). |
| **H7** destination path and checksum | After H6 | Owner or test reads the viewer | n/a | n/a | Entry `path` matches `^invoices/2026/[a-z0-9-]+/2026-11-01_[a-z0-9-]+_[a-z0-9-]+_<document-uuid>\.txt$` (suggested policy `invoice-filing-v1`) | Same after restart | The checksum equals the published value. The size equals the published size. **[GTC]** Contents are not compared, because no bytes were sent. | C, O |

### 5.2 Notes on exactness

- **[EV]** The plan suggestion path includes the full document UUID (`docs/INVOICE_FILING_PLANS.md`), so the exact path is run-specific. Assert by pattern. If a fixed path is needed, use a manual plan (`invoices/manual/synthetic-e2e-001.txt`).
- **[EV]** `canonical_path` lower-cases, so the destination records the lower-case path.

## 6. Restart and crash-point matrix

Notation: "kill" is `docker compose kill -s KILL <service>` (a real SIGKILL to PID 1). "stop" is `docker compose stop` (SIGTERM, then SIGKILL after the grace period). "start" is `compose up -d --wait`. Never use `down -v` in these scenarios, because that destroys the evidence.

**Time handling.** Real recovery of a crashed claim takes about 6-7 minutes (5-minute `IN_FLIGHT_DEADLINE`, 1-minute `RECONCILE_INTERVAL`, a 30-second pass). Two options:
- **Compressed (CI, mandatory):** age the persisted claim through a privileged fixture script run in the `migrate` container. It disables `butler_filing_guard`, backdates `attempt_started_at` or `next_attempt_at`, and re-enables the trigger. This is the same technique as `age()` and `due()` in `test_filing_fence_postgres.py` lines 29-55. It is a test technique and must be labelled so. Real processes and real restarts still occur; only the clock is compressed.
- **Real-time (owner manual and one optional CI diagnostic):** wait about 7 minutes. This proves the unmodified constants.

**[NBR]** `filing_worker.main()` needs an optional `--interval` (default 30) so a container run does not need to wait 30 seconds per pass. The default must not change.

| ID | Crash or restart point | How to reach it, deterministically | Expected state at the point | After restart and recovery | Duplicate-effect check | Layer, label |
|---|---|---|---|---|---|---|
| **R0** | Request committed, worker not yet started | Do H5, keep the worker stopped, then stop all services including Postgres and the sidecar, then start all | `pending`, `attempts=0`, destination empty | Start the worker: `filed` once. History `requested, attempted, filed`. | Calls log length 1, effects 1 | C: **[NBR]** |
| **R1** | After terminal success: full stack stop and start | After H6: `compose stop` (all services), then `compose up -d --wait` | `filed`, `resolved_at` set | The UI after re-sign-in (the session is DB-backed) still shows `filed`. The destination viewer shows the same entry, unchanged. No new `attempted` event. | Effects log still 1 | C: **[NBR]**. Whether the browser cookie survives the API restart is **[ENV]** (sessions are in `auth_sessions`), so assert re-login works rather than assuming the cookie survives. |
| **R2** | Claim committed, effect not applied: **before-effect** kill | Sidecar `hold-before-effect`. Start the worker. Wait for `ctl status` `held=true`. `kill filing_worker`. Release the hold or `ctl clear`. | `pending`, `attempts=1`, claim in flight. Destination has 0 entries. | Start the worker inside the in-flight deadline: result `skipped`, no change. After the deadline (backdated for CI): `unknown` (`ambiguous_outcome`). After the reconcile interval: lookup answers absent, so `pending` with `reconciled_absent`. Then the worker retries and the result is `filed`, `attempts=2`. Events match `FULL_HISTORY = ["requested","attempted","unknown","reconciled","attempted","filed"]`. | Exactly one entry. Calls log shows 2 PUTs (the first never applied). | C: **[NBR]**. In-process equivalent: **[EV]** `test_filing_restart_postgres.py:91`. |
| **R3** | Effect applied, outcome not recorded: **after-effect** kill | Sidecar `hold-after-effect`. Start the worker. Wait for `held=true`. `kill filing_worker`. | `pending`, in flight, `attempts=1`. Destination has **1** entry. | Start the worker: `skipped` inside the deadline. After the deadline: `unknown`. After the reconcile interval: lookup finds the key, so `filed` via a `reconciled` event, `attempts=1`. | Exactly one entry. Calls log has 1 PUT. No second write. | C: **[NBR]**. **[EV]** `test_filing_restart_postgres.py:120`. |
| **R4** | API restart while pending | H5 with the worker stopped. `kill api` (or `stop api`). `start api`. | `pending` | Re-login, status `pending`. Then start the worker, so `filed`. | One entry | C, B: **[NBR]** |
| **R5** | API and worker both killed, then both restarted (the owner's "stop worker and application") | During R3's held state, `kill filing_worker` **and** `stop api`. Start both. | As R3 | As R3, plus the UI shows the reconciled `filed` | One entry | C, O: **[NBR]** |
| **R6** (optional diagnostic) | Postgres restart while the worker is in flight | `hold-after-effect`, then `stop postgres`, release, `start postgres` | The claim was committed before the effect. The finish transaction fails, so the pass counts an error. The row remains in flight. | Recovers as R3 | One entry | C: **[NBR]** diagnostic |
| **R7** (optional diagnostic) | Sidecar restart | After H6: `stop`, `start` the sidecar only | Entry persists (volume) | `lookup` finds it. Lookup during the outage returns `UNAVAILABLE`, so a pending reconcile stays `unknown` and is never `failed`. | One entry | C: **[NBR]** |
| **R8** | In-process claim committed, effect not yet sent | Cannot be paused from outside a container | Covered by `test_filing_postgres.py:121` (claim commits before the effect) and `test_filing_restart_postgres.py:91` | n/a | n/a | PS only. **[GTC]** at container precision. |
| **R9** | Effect applied and response received, DB finish not yet committed | Cannot be paused from outside a container | Covered in-process by `test_filing.py:622` and by the `after_effect` hook, which is before the return of `put` | n/a | n/a | PS only. **[GTC]** at container precision unless a new test hook is added, which is not recommended in product code. |

**Wording rule for any report:** "survived a real restart" is claimed only for R0, R1, R4 and R5 results. The existing PS tests prove worker-process death plus fresh-process recovery against a directory ledger, not an application restart. An in-process test never proves a restart.

## 7. Authorization and privacy negative-test matrix

All of these must show **no `filing_executions` row created (or no row changed), no destination write, and an audit event with the stated type** unless noted. Fixture: `e2e-owner` (`member_a_private`), `e2e-peer` (same scope, a different user), `e2e-reader` (`household_shared` only), `e2e-stranger` (no relevant grant), `e2e-admin` (technical admin without the private grant), and a revoked-user fixture. Seed through the privileged migrate container, following `browser-fixtures.py` ("browser-revoked" with `revoke` and `disable` actions).

| ID | Case | Trigger | Expected API / UI | DB + audit | Destination | After restart | Existing coverage |
|---|---|---|---|---|---|---|---|
| **A1** | Peer with the same private scope | The peer calls `POST /filing/request` for the owner's document | 404 or 403 (the source filter hides it, otherwise `owner_denied`). The UI never offers the control. | Audit `filing.not_found` or `filing.owner_denied`. No row. | None | Same | **[EV]** `test_filing.py:143` (accepts 403 or 404). Add the assertion of the exact audit type. |
| **A2** | Shared-scope reader of a shared document | Reader requests filing | 403 `filing.owner_denied`. The UI control is absent. | `filing.owner_denied`. No row. | None | Same | **[EV]** in code (`filing.py` lines 284-285). Add a test. |
| **A3** | No scope grant | Stranger calls request with the owner's scope | 403 `filing.scope_denied` | `filing.scope_denied` | None | Same | **[EV]** in code. No filing-specific test found. |
| **A4** | Grant revoked **before** request | Revoke the owner's scope via the fixture, then request with the old session | 403 `filing.scope_denied` or 401 | Audit denial. No row. | None | Same | **[EV]** code, uncovered by a filing test. |
| **A5** | Grant revoked **after** request, before claim | H5 (worker stopped), revoke the scope, start the worker | UI shows `cancelled`, reason `scope_unavailable` | Event `cancelled`, `authorization_consumed_at` stays NULL, `attempts=0` | **0 entries** | Same | **[EV]** code (`inspect()`). The owner-inactive variant is covered by `test_filing_restart_postgres.py:300`. |
| **A6** | Revoked or expired session | Log out or revoke the session in the fixture, then POST | 401 `filing.session_denied` | Audit denial. No row. | None | Same | **[EV]** code. Uncovered for filing request. Expiry needs a privileged time shift on the container. |
| **A7** | Missing or wrong CSRF | Omit or alter `X-CSRF-Token` | 403 `filing.csrf_denied` | Audit denial. No row. | None | Same | **[EV]** code, no filing-specific test found. |
| **A8** | Missing, false or wrong-type acknowledgement | Omit each of the two flags in turn, send `false`, `1`, `"true"` | 422 (request-model validation). The UI button is disabled until both boxes are ticked. | No row. Whether the generic 422 handler writes an audit row is **[ENV]**. Do not assert an audit row without checking. | None | Same | **[EV]** `test_filing.py:123` (parametrised, rows empty). |
| **A9** | Stale document revision | Edit the document (revision increments), then send the old `expected_document_revision` | 409 `filing.source_changed`. The UI says to reload. | Denial audit. No row. | None | Same | **[EV]** `test_filing.py:123` (revision cases). |
| **A10** | Stale review/invoice revision | Re-review the fields, then send the old `expected_review_revision` | 409 `filing.review_changed` | Denial audit. No row. | None | Same | **[EV]** `test_filing.py:123` |
| **A11** | Stale plan | Withdraw or re-plan after approval, then request | 409 `filing.plan_not_approved` | Denial audit. No row. | None | Same | **[EV]** `test_filing.py:132` |
| **A12** | Plan changed after request, before claim | H5, then re-plan, then start the worker | `cancelled`, reason `plan_changed` | Event `cancelled`. Not consumed. | 0 entries | Same | **[EV]** `test_filing.py:242, 465` |
| **A13** | Repeated request | Send the identical request twice | 200 with `replayed:true` and the same filing id | Audit `filing.replayed`. Still one row. | One entry only | After restart the same | **[EV]** `test_filing.py:90` |
| **A14** | Concurrent requests from two sessions of one user | Two logins, two simultaneous POSTs | One 201 and one 200 `replayed:true`. The source and review `FOR UPDATE` serialise them. Alternatively a 409 `filing.destination_taken` is acceptable. Never two rows. | Exactly one `filing_executions` row | At most one entry | Same | **[EV]** reasoning from the code. `test_filing_postgres.py:557` covers different documents on one destination only. A same-document, two-session test is a gap. |
| **A15** | Cross-user visibility | The peer, reader and stranger call `query` and `history` with the owner's filing id | `query` returns 200 with no such item, or 403. `history` returns 403 or 404. The UI shows nothing. | Audit `filing.query`/`filing.not_found` | n/a | Same | **[EV]** `test_filing.py:143` |
| **A16** | Admin without the private grant | The admin queries or requests | Denied (`scope_denied`) | Audit denial | n/a | Same | **[EV]** by `authority()`. Uncovered for filing. |
| **A17** | Audit and response content scan | After H1-H6 and every failure scenario, scan every `audit_events.metadata_json/after_json/before_json`, `filing_execution_events.snapshot` and every filing API response for: the invoice field values, the logical path and its segments, the filename, the attachment bytes and the destination key | None found. Allowed fields: `revision, state, attempts, reason`, ids, scope, timestamps. | Scan result empty | n/a | Same after restart | **[EV]** by design (`record_event`), partial test `test_filing.py:90`. A full scan as an independent assertion is **[NBR]** test work. |
| **A18** | Sensitive path in sidecar logs | Scan sidecar and worker container logs after the run | The invoice fields are absent. The logical path appears in the sidecar record by design (synthetic). The worker log must not print paths. | n/a | n/a | n/a | **[EV]** the worker prints counters only (`filing_worker.py` lines 291-294). The adapter is new, so scan it. |
| **A19** | UI gating | A non-owner views a shared reviewed document | No "Request filing" control. A plan in `proposed` or `withdrawn` state also has no control. | n/a | n/a | n/a | **[NBR]** (`FilingPlanPanel` has `canEdit`) |
| **A20** | Plan approval does not authorize | After H4 | Zero filing rows and `execution_authorized:false` | none | Empty | Same | **[EV]** `test_filing.py:68, 504`; `invoices.spec.ts` |

**Not provable here.** **[GTC]** Network-level or process-level isolation of other containers' memory. Real cross-user leakage beyond the filing surfaces (the broader suite is the `test_mvp_leakage*` set, whose filing operations are listed as uncovered at `PROJECT_MASTER.md` line 111).

## 8. Failure and reconciliation matrix

| ID | Scenario | Trigger | State path | Destination | After restart | Existing coverage |
|---|---|---|---|---|---|---|
| **F1** | Failure **before** effect (transient) | Sidecar `transient-once` | `retry_scheduled` (`transient_error`), then after backoff `pending`, then `filed`. Events include `retry_scheduled`. | One entry, after the retry | Same | **[EV]** in-process `test_filing.py:211`. Container: **[NBR]** |
| **F2** | Bounded retry exhaustion | Sidecar `transient-n` (3) | `retry_scheduled` x2, then `failed` `attempts_exhausted` (`attempts=3`). Terminal. | 0 entries | `failed` stays `failed` | **[EV]** `test_filing.py:211`, `test_filing_fence_postgres.py:226` |
| **F3** | Effect succeeded, worker died before recording | R3 | `unknown`, then `filed` via `reconciled` | 1 entry | See R3 | **[EV]** PS `test_filing_restart_postgres.py:120` |
| **F4** | Timeout where the effect was applied | Sidecar `timeout-applied` | `unknown` (`ambiguous_outcome`), then `filed` by lookup. No second PUT. | 1 entry, calls log 1 | Same | **[EV]** `test_filing.py:159`, `test_filing_postgres.py:156`. Container: **[NBR]** |
| **F5** | Timeout where the effect was lost | Sidecar `timeout-lost` | `unknown`, then lookup **absent**, then `pending` (`reconciled_absent`), then `filed` | 1 entry (second attempt) | Same | **[EV]** `test_filing_postgres.py:531` |
| **F6** | Lookup **inconclusive** | After R3 reaches `unknown`, sidecar `lookup-unavailable` and `lookup-error`, then several due passes | Stays `unknown` (`ambiguous_outcome`). Never `failed`, never a resend. A pass backoff of 15 minutes applies (`BACKOFF[-1]`). | Unchanged, entries and calls log stable | Stays `unknown` across a stack restart, then resolves after repair | **[EV]** PS `test_filing_restart_postgres.py:142, 165, 284` |
| **F7** | Lookup **present** | Lookup restored after F6 | `unknown` to `filed` (`reconciled`) | 1 entry | Same | **[EV]** same tests |
| **F8** | Lookup **absent** | Lookup restored with no entry | `unknown` to `pending` (`reconciled_absent`), then `filed` once | 1 entry | Same | **[EV]** `test_filing_restart_postgres.py:165` |
| **F9** | Collision / no overwrite | `preseed-collision <plan path>` by another key, then run | `failed`, reason `collision`, terminal. The pre-seeded entry is untouched. | The pre-existing entry byte-identical, effects log has no new line | `failed` after restart | **[EV]** `test_filing_restart_postgres.py:238`, `test_filing.py:229, 412` |
| **F10** | Cross-scope same manual path | Two filings, different scopes, same manual path | The second ends `failed` `collision` at the destination although the DB reservation passed | One entry | Same | **[EV]** from the code only (section 3.4). The behaviour is real but no test was found. **Test needed.** |
| **F11** | Forgetting while `pending` | Forget the document before the worker claims it | `cancelled` (`source_changed`), then a `scrubbed` event. Snapshots NULL. | 0 entries | Same | **[EV]** `test_filing.py:307`, `test_filing_postgres.py:454` |
| **F12** | Forgetting while `unknown` | Forget during `unknown` | Reconciliation stops, `cancelled` | The destination may already hold an entry. The effect is **not** recalled. | Same | **[EV]** `test_filing_postgres.py:763` |
| **F13** | Forgetting after `filed` | Forget the document | `scrubbed` event, key nulled, snapshots NULL, API reports `scrubbed:true` with no document or plan link | The destination entry **remains**. This is the documented limit. | Same | **[EV]** `test_filing.py:294, 516`, `test_filing_postgres.py:669`. The tests must assert the residual entry exists and is described honestly. |
| **F14** | Stale worker after a newer claim | R-series with two workers | The stale result is discarded (`skipped`) | One entry | n/a | **[EV]** `test_filing_restart_postgres.py:215, 262` |
| **F15** | Cancel rules | Cancel a `pending`, unclaimed filing, or one in flight | 200 for unclaimed, 409 `not_cancellable` for in-flight or `unknown` | n/a | n/a | **[EV]** `test_filing.py:254, 281`, `test_filing_restart_postgres.py:318` |
| **F16** | Retry after a failed filing for the same plan revision | Re-request the same plan revision after `failed` | 200 `replayed:true` returning the `failed` row, not a new attempt. A retry needs a new plan revision. | n/a | n/a | **[EV]** code (`existing` lookup). The UI must explain this. |

**False-success guard.** Every scenario's pass condition requires the destination evidence to agree with the DB state. A `filed` row with no entry, or an entry with a `failed` row, is a fail. Neither the DB alone nor the destination alone is sufficient.

## 9. Owner-facing manual test script

Everything here uses synthetic users and data only. Script names (`scripts/e2e-filing.sh` and so on) and new UI labels are **[PTA]/[NBR]** proposals for A3 to supply. The existing UI labels were read from `emails.spec.ts` and `invoices.spec.ts` and are **[EV]**. Do not use the owner's real data, real mailbox, real NAS or real credentials.

### 9.1 Deterministic fixture identity and checksum

**[PTA]** A3 supplies a generator script that emits fixed bytes with no clock, no randomness and no locale dependence. The published manifest records three values:
- `MESSAGE_SHA256`, `MESSAGE_BYTES`: the whole `.eml`.
- `ATTACHMENT_SHA256`, `ATTACHMENT_BYTES`: the decoded attachment.
- The attachment filename and the expected extracted fields.

Content, designed to satisfy the verified parser constraints (section 3.5):
- Hand-written template with explicit `\r\n` line endings, no library formatting.
- Headers once each: `From: billing@synthetic-vendor.invalid`, `To: household@example.invalid`, `Subject: Synthetic E2E invoice forwarded`, a fixed `Date:`, a fixed `Message-ID: <synthetic-e2e-001@example.invalid>`, `MIME-Version: 1.0`, and `Content-Type: multipart/mixed; boundary=synthetic-e2e-boundary-001`.
- Part 1: `text/plain` body "Synthetic forwarded original".
- Part 2: a single attachment, `Content-Type: text/plain`, `Content-Disposition: attachment; filename="synthetic-invoice-e2e-001.txt"`, `Content-Transfer-Encoding: base64`, base64 wrapped at 76 characters.
- Attachment text, same five-line layout as the existing spec so the candidate line numbers 1-5 are known:
  ```
  Issuer: Synthetic E2E Vendor
  Invoice number: E2E-001
  Invoice date: 2026-11-01
  Total: 19.00
  Currency: EUR
  ```
- Keep it under the 32,000 character and 131,072 byte limits (trivially true).

**How the checksum is published and kept honest:**
1. The manifest values are committed next to the generator as plain constants.
2. Two **different** tools compute them independently (for example `sha256sum` over the file and `base64 -d | sha256sum`, and `openssl dgst -sha256`). A4 or A5 recomputes them. A3's own test must not be the only source.
3. The owner is shown the values in the docs and can recompute with their own `sha256sum`.
4. A re-import of identical bytes in the same owner and scope is a replay by design, so the owner script resets the stack between runs. It does not vary the bytes.

### 9.2 Environment startup and readiness

Use a dedicated disposable stack. Never reuse a development database.

1. Start the owner stack with one documented command, for example `scripts/e2e-filing.sh up`. **[PTA]** It must: use a distinct compose project name and ports, set `BUTLER_ENV=test` and a `butler_test_*` database (the worker refuses otherwise), generate throwaway passwords, build the sidecar and the worker, and use no bind mounts.
2. Readiness (the script prints PASS or FAIL for each; the owner does not need SQL):
   - `GET /api/v1/health` returns OK.
   - The destination identity reports `kind=butler-synthetic-filing-ledger` and the run id.
   - The destination is empty: "0 entries".
   - The worker is running and reports the synthetic-destination guard satisfied.
   - The data network is internal (no outbound access).
   - The destination volume is a named volume, not a host path.
3. **Provisioning.** The script creates the synthetic users through the privileged migrate container (pattern: `scripts/browser-fixtures.py`) and prints their names: `e2e-owner` (`member_a_private`), `e2e-peer` (same scope), `e2e-reader` (`household_shared` only), `e2e-stranger` (no grants). The passwords are printed once and are synthetic.

### 9.3 The journey (owner actions and what they should see)

| # | Action | Expected visible state |
|---|---|---|
| 1 | Open the printed local HTTPS address. Sign in as `e2e-owner`. | Navigation "Local records" appears. Choose Documents and scope `member_a_private`. |
| 2 | "Import forwarded email…". Title "Synthetic E2E invoice". Choose the generated `.eml`. Press "Import email attachment". | Region "Offline email import" says "Attachment imported unreviewed". |
| 3 | Press "Open imported document". | The selected document shows "Issuer: Synthetic E2E Vendor". The subject line text is not used as content. |
| 4 | Repeat step 2 with the **same file** and a different title. | The region says "Exact email already imported". Opening the document shows the **original** title. No second document appears. |
| 5 | In "Original email provenance", press "Load original email provenance". | It says "matches current bytes". Optionally download the original email and compare its checksum to the published `MESSAGE_SHA256`. |
| 6 | "Correct and review", tick the checkbox, "Save document". Select the document, "Load invoice review", "Prepare invoice candidates", press "Use Issuer / Invoice number / Issue date / Total / Currency candidate at line 1 / 2 / 3 / 4 / 5", tick the attestation box, "Save invoice field review". | The fields show Synthetic E2E Vendor, E2E-001, 2026-11-01, 19.00, EUR. |
| 7 | "Suggest filing plan". | "Plan status: proposed". A path like `invoices/2026/synthetic-e2e-vendor/…txt` and the original SHA-256 equal to the published `ATTACHMENT_SHA256`. Compare them. |
| 8 | Tick both approval boxes. Press "Approve filing plan only". | "Plan status: approved" and "No file has been written". **Nothing has been filed yet.** The destination status check shows 0 entries. |
| 9 | **[NBR]** In the new filing control, tick both acknowledgements (the destination is synthetic, and this exact plan) and press the request button. | A status line shows **pending**, naming the synthetic destination. The destination check still shows 0 entries if the worker is stopped. |
| 10 | Start the worker (`scripts/e2e-filing.sh start-worker`). Refresh or wait. | Status becomes **filed**. |
| 11 | Run `scripts/e2e-filing.sh check`. | It prints "Destination holds 1 entry", the logical path, the entry's checksum and size, "matches the published checksum: YES" and "entries for this filing: 1". The owner may also open the read-only destination viewer on the loopback address. |
| 12 | **Restart.** Run `scripts/e2e-filing.sh restart` (stops the worker, the application and the database and the destination, then starts everything). Sign in again and open the same document. | Status is still **filed**. `check` shows the **same** one entry and checksum. "No second entry" is reported. |

### 9.4 Interrupted-effect restart (the harder test)

1. Reset to a fresh stack and repeat steps 1-9.
2. Run `scripts/e2e-filing.sh inject hold-after-effect`. Start the worker. The script reports "destination applied the filing and is holding its reply".
3. Run `scripts/e2e-filing.sh kill-worker-and-app`. The UI shows **pending** for a while. This is correct, not a fault.
4. Run `scripts/e2e-filing.sh start`. Then wait. Real timing is about 5 minutes for the claim to be recognised as stale, then about 1 more minute for the reconciliation. An optional `--compress-time` switch (a labelled test shortcut) skips the waiting. State clearly to the owner when it was used.
5. Expected: the status passes through **unknown** ("outcome not known") and ends **filed**. `check` reports exactly **1** entry, and "writes attempted: 1". A second write would be a failure.

### 9.5 Inconclusive-outcome test without risking a false success

1. Repeat 9.4 up to the point where the status is **unknown**.
2. Run `scripts/e2e-filing.sh inject lookup-unavailable`. Wait for two checking passes.
3. Expected: the status stays **unknown**. It must never show **filed** or **failed** while the destination cannot answer. `check` shows the entry count unchanged.
4. Run `scripts/e2e-filing.sh inject clear`. After the next pass the status becomes **filed**.

### 9.6 Duplicate, collision and protection spot checks

- Press the request control again after step 10. Expected: the UI says the request already exists. There is still 1 entry.
- Sign in as `e2e-peer` and `e2e-reader`. Open the document list. Expected: no filing control or status appears for `e2e-reader`. The `e2e-peer` sees no filing of the owner's.
- Edit the document, then retry the request from a stale page. Expected: "The source or review changed" and no new filing.
- Optional collision: `inject preseed-collision`, then file a second invoice to the same manual path. Expected: **failed**, and the pre-existing entry is unchanged.

### 9.7 Cleanup and reset

`scripts/e2e-filing.sh down` removes the containers and **volumes** and prints "destination volume removed: YES". It must refuse to run against anything other than the disposable project name. Between runs, always reset to a fresh stack, because replay protection makes the same message impossible to import twice for the same user and scope.

### 9.8 What the owner has actually established, and what not

If steps 1-12, 9.4 and 9.5 pass, the owner has seen the journey on a **synthetic** stack. The record proves nothing about a real NAS, filesystem, mailbox or provider. Acceptance is the owner's decision and must name the environment and scope. Nothing in this script records it.

## 10. CI execution and coverage plan

### 10.1 Does CI currently run the needed phases in sequence?

**No. [EV]**

- The `postgres` job runs the PS restart tests, so worker-process-death recovery against a durable directory ledger is already in CI.
- The `containers` job runs `scripts/test-containers.sh`, which includes the emails and invoices specs (line 138) but has **no filing worker, no filing UI, no durable destination and no restart or kill step**.
- The only restart-like operations in CI are in the PS tests (subprocess SIGKILL).

### 10.2 Scenario to layer map

| Scenarios | Layer | Existing infra | Gap |
|---|---|---|---|
| Unit and API semantics (A8-A13, F1-F2, F11, F13-F16) | U | `test_filing.py` (SQLite, in `backend` job) | Add the missing CSRF, session, scope-denied and same-document concurrency cases (A3, A4, A6, A7, A14, A16) |
| DB guards and grants (A20, F9, F10 seal parts) | P | `test_filing_postgres.py`, `test_filing_fence_postgres.py` (in `postgres` job) | Add F10 (cross-scope collision) and the scrub-while-effect-residual check (F13) |
| Worker crash windows R2, R3, R8, R9, F3, F6-F8, F14 | PS | `test_filing_restart_postgres.py`, `restart_support.py` | None for worker crash points. Keep as the precise-window layer. **Do not weaken.** |
| New adapter correctness (put and lookup mappings, hard timeout, handshake refusal) | U + PS | None | New unit tests for the HTTP adapter mappings (including "bare 404 is unavailable, not absent") and for the worker's refusal to start with a wrong host, a wrong identity or a non-test env |
| H1-H7, A1, A2, A15, A19 UI | B | `emails.spec.ts`, `invoices.spec.ts` patterns | New `frontend/e2e/filing.spec.ts` (**[NBR]**) in its own fresh-login phase |
| R0, R1, R4, R5 real restarts, R2, R3 container crash windows, F4-F8 container | C | None | New phase in the containers flow |
| A5, A4, A6 (revocation, session) in the stack | C | `browser-fixtures.py` `revoke`/`disable` pattern | A new fixtures action |
| Owner script | O | None | Section 9 |

### 10.3 Minimum additional CI (with reasons)

1. **A new compose override and phase** `filing_compose` in `scripts/test-containers.sh`, or a new `scripts/test-filing-e2e.sh` called from it. It must start a **fresh** stack, because the real login limiter has a 30-login budget per source window and the script's comments say fresh stacks are the established way to preserve it. The sequence:
   1. Start the stack with the destination, the worker and the browser flags.
   2. Seed users.
   3. Run `filing.spec.ts` up to the `pending` and `filed` assertions.
   4. Run R0, R1, R4 and R5 (restart while preserving volumes).
   5. Run R2 and R3 with time compression.
   6. Run the independent evidence check (destination viewer versus the published checksum, calls-log counts, and the DB's event sequence) in a final step that does not import the spec's helpers.
   7. `down --volumes`.
   Also assert that the phase fails if the worker never started. A deliberate skip must not read as a pass (`docs/CI_COMPUTE.md`).
2. **Duration and timeout.** I did not measure phase durations. The `containers` job is capped at 25 minutes already. The estimate for the new phase with time compression is 8-12 minutes (cold build of two images, three restarts with `--wait`, and a browser). **[ENV]** A3 must measure it. If it pushes the job beyond the limit, give it its own job with the same `ci_scope.py` selection and add it to `needs` in the `ci` job and to `scripts/ci_gate.py`. I did not read `ci_gate.py`, so I do not know what that change requires. The cheaper first choice is a phase in the existing job and a raised `timeout-minutes`.
3. **Real-time diagnostic.** One optional run with unmodified constants (about 7 minutes), in `workflow_dispatch` or the weekly schedule only, not on every PR. It proves the unmodified constants against a real container kill.
4. **Independence in CI.** The evidence check must read the destination through the sidecar's own viewer and recompute the expected checksum from the committed manifest, not from the DB or from the spec's helper.

### 10.4 Mandatory versus optional

| Mandatory (blocks the PR) | Optional diagnostic |
|---|---|
| U and P additions above. The PS suite unchanged. Adapter unit tests. Browser spec H1-H7, A1, A2, A19. Container R0, R1, R4, R5, R2, R3 with time compression. F6-F9 in the container. The independent evidence check. | R6 (Postgres restart), R7 (sidecar restart), the real-time R2/R3 run, F10 in the container, the sidecar log scan A18, mobile viewport check of the new control. |

## 11. Observable acceptance criteria

Each is observable without reading source. For acceptance the owner decides, naming environment and scope.

1. **AC1** A fresh stack starts with an empty destination, and the filing worker, the application, the database and the destination are all running.
2. **AC2** An identical second import returns "Exact email already imported" and creates no second document, envelope or filing.
3. **AC3** The invoice fields and the original email provenance are shown. The downloaded original equals the published `MESSAGE_SHA256`.
4. **AC4** Approving the plan leaves the destination empty and the filing list empty, and the plan says nothing is filed.
5. **AC5** The request control requires both acknowledgements, is separate from plan approval, and is available only to the owner of an approved plan.
6. **AC6** After the request, the status is `pending` and the destination is still empty until the worker runs.
7. **AC7** After the worker runs, the status is `filed`, the destination holds exactly one entry keyed by the filing id, and its checksum and size equal the published `ATTACHMENT_SHA256` and size.
8. **AC8** After a full stack stop and start, the status is still `filed`, the destination entry is unchanged and no second entry or second write exists.
9. **AC9** After the worker is killed with the effect applied but unrecorded, restart leads to `unknown` and then `filed`, with exactly one write.
10. **AC10** After the worker is killed with no effect applied, restart leads to `unknown` and then, only after a conclusive "absent", to `filed`, with exactly one effect.
11. **AC11** While lookup is unavailable the status stays `unknown`, never `filed` and never `failed`, and the destination does not change.
12. **AC12** A collision yields `failed` with `collision`, and the pre-existing entry is untouched.
13. **AC13** A peer, reader, stranger, revoked user, stale revision or missing acknowledgement can never create or alter a filing and never sees another user's filing.
14. **AC14** Audit and history contain no invoice field, no path, no filename and no attachment content.
15. **AC15** Every claim in the report names its limits: synthetic, no real filesystem, checksum-only.

## 12. Evidence limitations and unresolved design questions

### 12.1 What I did not read or run

- Not run: any test, the stack, a browser, `make check`, or any container command.
- Not read in full: `identity.py`, `documents.py`, `invoice_review.py`, `invoice_filing.py`, the body of each trigger in migration 0034, `ci_gate.py`, `ci_scope.py` (only the `JOBS` and scope lines), `release-candidate.yml`, `Dockerfile`s, `SECURITY.md` and `DECISIONS.md` (grep only), `specs/056`, `057`, `058`, `068` bodies (I relied on their docs and on code), `docs/TESTING.md`, and `FEATURE_REGISTER.md` (I read the master and acceptance rows instead). The PDF extraction path was not read.
- Test bodies read: the restart suite, the fence helpers, the MVP-03 journey top, and snippets of `test_filing.py` and `test_filing_postgres.py`. For the others I read names only.

### 12.2 Limitations of any result from this design

- **[GTC]** Synthetic only. No claim about a real NAS or filesystem, partial writes, permissions, capacity or case folding.
- **[GTC]** Checksum-only. Nothing proves stored bytes equal the original bytes.
- **[GTC]** Container-level pause between "response received" and "DB finish committed" (R9) and between "claim committed" and "request sent" (R8) cannot be forced from outside. Only the in-process and subprocess harness covers them.
- **[GTC]** Compressed time uses backdated rows with the seal trigger temporarily disabled by an administrator. It proves the logic and the real restarts, not the unmodified clock. The real-time diagnostic covers that separately.
- **[GTC]** A single passing run proves nothing about rare races. The existing bounded repeated-contention tests (`test_filing_postgres.py:992, 1030`) are the only race evidence.
- **[GTC]** An in-process test never proves a restart. The PS tests prove worker-process death, not an application restart.
- The browser cookie surviving an API restart is **[ENV]**.
- Whether the generic 422 validation handler writes an audit row is **[ENV]**.

### 12.3 Unresolved design questions (for A3 and A1, not for me to decide)

- **UD1** Where does the UI poll for status? `POST /filing/query` filtered by `document_id` exists. Is manual refresh enough, or does the owner expect automatic polling?
- **UD2** The destination viewer is independent of the app. Does the owner accept that the checksum shown on the destination side comes from the sidecar rather than from the app UI?
- **UD3** The worker `--interval` flag and the adapter timeout are product code changes inside a spec (069) that excluded them. Which spec or amendment carries them?
- **UD4** Spec 069 and `PROJECT_MASTER.md` currently say "no web screen" and "durable synthetic ledger across restarts" are out of scope. Per `AGENTS.md`, an owner-approved decision must be reflected in the master. This is for A1 and A6, and I made no change.

## 13. Precise implementation handoff to A3

All items are **[NBR]/[PTA]** and are proposals to be built under repository rules. I implemented nothing.

1. **Destination adapter.** In `backend/app/` add an adapter class implementing `put(key, path, sha256, size)` and `lookup(key)` over the HTTP ledger API (section 4.3, item 5). Keep `filing.SyntheticDestination` unchanged for unit tests. Add unit tests for every status mapping, including a bare 404 and a wrong `ledger_id` returning `UNAVAILABLE`, and a hard timeout below `filing.IN_FLIGHT_DEADLINE`.
2. **Worker entry.** In `backend/app/filing_worker.py` `main()` (lines 276-299), add destination selection and the pre-flight handshake (section 4.3, item 7), and an optional `--interval`. Do not change the existing guard (lines 284-287) or the default 30 seconds.
3. **Sidecar.** A small stdlib server script and a control command (section 4.3), mounted read-only in the backend image like `scripts/synthetic-answer-model.py`. Reuse the `Ledger` publish and log logic from `backend/tests/restart_support.py` lines 34-111. Share one implementation rather than copying, if the repo's rules allow production code to depend on test code. Otherwise copy and keep a parity test.
4. **Compose.** `infra/core/filing-synthetic.override.yml` with `synthetic_filing_destination`, `filing_worker` (profile or explicit), an `internal: true` destination network, a named volume, `read_only`, `cap_drop`, `no-new-privileges` and limits. Do not touch the base `compose.yml`.
5. **Frontend.** In `frontend/src/FilingPlanPanel.tsx` (or a sibling component), add the separate "Request filing" control for an approved plan with the two acknowledgements and a status display, plus `frontend/src/filing-api.ts` calling `/api/v1/filing/request` and `/query`. Validate responses as `invoices-api.ts` does. Keep "Approve filing plan only" unchanged and keep `execution_authorized:false`. Handle 409, 422 and 401/403/404 with messages like `InvoiceError`.
6. **Fixture generator and manifest** (section 9.1), the seeding action for the new users, a `revoke` action for the grant-revoked scenarios, and a backdating action that disables and re-enables `butler_filing_guard` in the privileged container only.
7. **Tests to add:**
   - `frontend/e2e/filing.spec.ts` for H1-H7, A1, A2, A19 (and note the `inbox.spec.ts` regex at lines 65-66 if the control is reachable from the inbox).
   - The container phase for R0-R5 and F4-F9.
   - The filing-specific negative tests listed in section 7 as gaps (A3, A4, A6, A7, A14, A16, A17), and F10.
   - A test asserting the worker refuses to start with `staging`, `production`, a wrong host, a wrong identity and a non-`butler_test*` DB.
8. **CI.** Add the phase to `scripts/test-containers.sh` or a new job (section 10.3). Measure duration. Read `scripts/ci_gate.py` and `scripts/ci_scope.py` before adding a job.
9. **Docs.** When the owner has approved the amendment, update the authoritative sources in precedence order: `PROJECT_MASTER.md` Gate 7 (the delivered, tested and verified facts kept separate), `docs/FEATURE_REGISTER.md` rows if affected, `docs/MVP_ACCEPTANCE.md` row 7, `docs/FILING_EXECUTION.md`, `docs/INVOICE_FILING_PLANS.md` and `specs/069-.../spec.md`. Regenerate derived views with `python3 scripts/build_feature_overview.py`. Never hand-edit `FEATURE_OVERVIEW.md` or `FEATURE_DASHBOARD.html`.
10. **Independence rule.** A3's own tests must not be the only evidence. The container phase's final check must recompute the expected checksum from the committed manifest and read the destination through the sidecar viewer.

## 14. Owner decisions still genuinely required

1. **Q1 Checksum-only or bytes.** The current interface sends no bytes, and `docs/FILING_EXECUTION.md` says so. Does "verify the destination effect and checksum" mean the recorded checksum (what exists), or must the destination actually store and re-hash content? The latter is a product change (a new `put` parameter and storage), and it changes what the sidecar holds.
2. **Q2 Spec amendment.** Spec 069 excludes a filing web screen and a durable synthetic ledger. Do you authorise amending it (and reflecting that in the master) so a UI control, a worker in the container stack and a durable destination are in scope?
3. **Q3 Time.** Is compressed time (backdated claims, labelled) acceptable for CI, with the full 6-7 minute real-time run kept as a manual or scheduled diagnostic? Or must the real wait be in every PR?
4. **Q4 Environment limit.** The worker refuses to run outside development and test. Do you accept that this journey is a disposable-stack capability only, with no production path?
5. **Q5 Attachment type.** Is a `.txt` invoice attachment (the type the existing email and invoice specs use) a faithful "invoice attachment" for this gate, or must it be a PDF? A PDF needs a deterministic PDF fixture and the PDF extraction path, which I did not examine.
6. **Q6 Forgetting after filing.** The synthetic effect cannot be recalled after forgetting (documented limit). Confirm this is accepted for the journey.
7. **Q7 Status wording for `unknown`.** What should the owner be told in the UI while the outcome is unknown? This is a product-copy choice, not an engineering one.

I claim no owner acceptance, and nothing here changes a gate status."
