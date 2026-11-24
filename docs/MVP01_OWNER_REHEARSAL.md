# MVP-01 owner rehearsal (Mac-local, synthetic) — spec 076

A named, disposable, single-stack Docker rehearsal on your Mac for the synthetic invoice journey. Contract and limits: [spec 076](../specs/076-mvp01-synthetic-invoice-journey/spec.md). Everything is synthetic and loopback-only; it is **not** acceptance, not a real integration and not production.

## Commands

```bash
bash scripts/mvp01-owner.sh start       # create private config, build images, start, seed the fixture, print the guide
bash scripts/mvp01-owner.sh status      # revisions, services, fixture checksum, CA fingerprint, identity, ledger counts
bash scripts/mvp01-owner.sh rebuild     # rebuild images from this checkout and recreate containers (data preserved)
bash scripts/mvp01-owner.sh restart     # container restart of api/web/caddy/workers/simulated model/PDF worker
bash scripts/mvp01-owner.sh restart --kill   # SIGKILL of api/workers/simulated model/PDF worker, then start again
bash scripts/mvp01-owner.sh pdf-worker stop     # simulate an offline PDF reader (kept across start/rebuild/restart); pdf-worker start repairs it
bash scripts/mvp01-owner.sh stop        # compose down; database, CA and synthetic ledger volumes are kept
bash scripts/mvp01-owner.sh reset       # DESTRUCTIVE, only this rehearsal; asks you to type the project name
bash scripts/mvp01-owner.sh scenario timeout-after-effect on   # optional synthetic failure controls
```

Application source is built into the images: **rebuild after every edit**. Source edits and host checks happen on the Mac; Docker runs the services and container-only checks.

## Identity of the environment

| Item | Value |
|---|---|
| Compose project | `local-assistant-core-mvp01-owner` |
| Database | `butler_test_mvp01_owner` (`BUTLER_ENV=test`), migration owner `butler`, runtime role `butler_runtime` with a distinct generated secret |
| URL / origin | `https://localhost:18444/` = `BUTLER_AUTH_ORIGIN`; HTTP probes `127.0.0.1:18081` (no credential form) |
| App subnet | `172.29.243.0/28` fixed; Caddy `172.29.243.2` is the only trusted proxy for the API |
| Services | postgres, migrate, role_setup, api, web, caddy, reminder_worker (restricted, real), filing_worker (restricted; durable synthetic ledger), synthetic_ledger_init, **synthetic_answer_model (simulated)** |
| Simulated parts | answer model = fixed script (no model, no inference, no outbound AI); calendar = one manual snapshot through the real API; filing destination = synthetic **metadata** ledger |

Single stack only: the fixed subnet and proxy-trust address cannot be shared. If another environment holds it (for example the default development stack `local-assistant-core-dev`/`butler-poc`), `start` names the conflicting network and refuses without stopping anything; stop that environment yourself first. Project names and ports alone do not isolate concurrent stacks, and the proxy allowlist is never loosened.

## Mounts (host source → container destination, purpose, mode)

| Source | Destination | Purpose | Mode |
|---|---|---|---|
| `infra/core/Caddyfile` | caddy `/etc/caddy/Caddyfile` | proxy configuration | read-only |
| `scripts/synthetic-answer-model.py` | synthetic_answer_model `/opt/synthetic-answer-model.py` | simulated cited-answer fixture | read-only |

No calendar fixture directory is mounted (the calendar is imported through the API). Named volumes (project-prefixed): `postgres_data`, `caddy_data`, `caddy_config` (private CA key), `synthetic_filing` (ledger, mounted only into `filing_worker` and its one-shot initializer, read-write). Nothing mounts `.env`, credentials, private records, the repository or your home directory. The script does not read the repository `.env`; it generates `.local/mvp01-owner/mvp01-owner.env` (mode 0600, git-ignored) used only for Compose interpolation.

## Credentials and certificate

- You choose the synthetic sign-in password at a hidden prompt on the first `start` (or set `BUTLER_MVP01_OWNER_PASSWORD` for that single command). It is hashed in the database and never stored or printed. Use a throwaway value, never a real password.
- Only the **public** development CA is exported to `.local/mvp01-owner/butler-mvp01-dev-root.crt`; the script prints its SHA-256 fingerprint. Compare, then import it yourself (Keychain Access, login keychain, "Always Trust"). The script never changes a trust store, never clicks through a certificate warning and never disables TLS verification. To retire the CA, remove that fingerprint from the keychain.
- Sign-in is rate limited per account (5 attempts per 15 minutes, successful ones included). The limiter is never cleared.

## Fixture

`.local/mvp01-owner/fixtures/invoice.eml` (copied from `scripts/mvp01-owner-fixtures/invoice.eml`), SHA-256 `a1b6c2eb631bfe14e6dbbeed559cba75acb0e5640b820a026110d78aee1a9d97`: a synthetic forwarded email with one text attachment — issuer "Synthetic Rehearsal Vendor", invoice `MVP01-2026-001`, dated 2026-11-20, due 2026-12-20, total **123.45 EUR**. `start` verifies this checksum before copying.

Seeded once and idempotently: users `mvp01-owner` (scopes `household_shared`, `member_a_private`) and `mvp01-peer` (`member_b_private`, random password never shown); agenda for **2026-11-24, Europe/Zurich** — task "MVP-01 synthetic: pay-check invoice MVP01-2026-001" (due 17:00) and calendar event "MVP-01 synthetic: family planning call" (10:00–11:00) — and a peer-private task carrying `PEER-PRIVATE-MARKER` that you must never see.

## Ordered journey

0. **Free the fixed subnet.** Only one stack can use `172.29.243.0/28`. If `start` refuses and names a Compose project (for example `butler-poc`), stop that environment yourself **without `-v`** so its data survives: `docker compose -p <that project> down`. The script never stops or removes anything outside this rehearsal. The loopback ports 18081/18444 must also be free.
1. Open `https://localhost:18444/`, sign in as `mvp01-owner` (no warning bypass); try a mobile-width window too.
2. Daily overview for 2026-11-24 / Europe/Zurich: the event and task once each; freshness and zone shown; no peer marker.
3. Import `invoice.eml` through *Import forwarded email* twice: one document, "Exact email already imported", original title preserved; inspect the email original.
4. Open the document, correct and mark it reviewed. Ask **"What is the total amount?"**: exact quotation `Total: 123.45` with document, revision, SHA-256 and line 5; open the current source. The selector is simulated. Add `synthetic-unavailable` to the question for an explicit unavailable answer.
5. Reminders are **enabled by default** with no preferences saved (Europe/Paris, quiet hours 22:00–08:00, at most 5 per day); saving unchanged preferences is refused by the server and the screen says nothing needs saving. In *Tasks and agenda*, select the task and scroll to the bottom of its details: the *Remind me in Butler* control is there. Schedule it a couple of minutes ahead (and outside the quiet hours of the chosen time zone). The reminder worker (30 s cycle) delivers it once; acknowledge it; the task stays open.
6. Invoice review: prepare candidates, confirm issuer, number, issue date, total, currency, leave **Due date Unknown**, save (a plan can only be *suggested* once issuer, invoice number and issue date are all confirmed and saved; the panel lists what is missing, otherwise use a manual destination); suggest the filing plan and approve it *as a plan only*. Nothing has been filed.
7. In *Synthetic filing execution*, read the bindings (document, source revision, plan revision, path, SHA-256, metadata-simulation limit), tick both acknowledgements and request the filing. It goes Pending → Filed (the worker cycles every 5 s). Open its history.
8. `restart`, then `restart --kill`. Sign in again, open the document and click *Load invoice review* (the filing panel appears only once the review is loaded): same records, review, plan, history, status **Filed**, one filing, and `status` shows ledger `effects: 1`.

Optional failure rehearsals before step 7 (`scenario`): `timeout-after-effect on` (effect lands, worker sees a timeout → *unknown* → reconciled to Filed with one effect), `timeout-before-effect on` (timeout without effect → conclusive absence → one retry), `lookup-unavailable on` (stays *unknown*, never retried blindly; `off` to resolve).

## Evidence labels

Process kill, container restart, host reboot and clean-host recovery are different things. `restart` is a container restart; `restart --kill` is a SIGKILL of the application/worker processes with PostgreSQL left running; a host reboot and a clean-host recovery are **not** exercised. Real-process SIGKILL tests against disposable PostgreSQL are in `backend/tests/integration/test_mvp01_journey_postgres.py`. The same journey can be checked through the API with `scripts/mvp01-owner-check.py` (see the script header); both are agent evidence, not owner acceptance.

## Stop and reset

`stop` keeps everything. `reset` also works when the generated config is gone (for example after deleting `.local/`) while the project's volumes remain: it then identifies the project by its exact Compose label and name prefix. Without the config only these checks apply: the project name is the fixed rehearsal name, every object carries that exact Compose label **and** name prefix, and you type the project name; the database-name and synthetic-marker checks need the config and are skipped (the printed list of containers and volumes is what you confirm). The Compose project name is global on this Mac, so `reset` also removes a rehearsal started from **another checkout** of this repository. It deletes, after you type the exact project name, only the containers, network and volumes carrying the `local-assistant-core-mvp01-owner` Compose label and prefix (verified before deletion) and `.local/mvp01-owner/`. It refuses to run if the generated config does not name the exact rehearsal database and synthetic marker. No prune, no other project, no images. Remove the old CA fingerprint from your keychain yourself.

## Second journey: the bad-connection day (spec 077)

A simulated outage on the same stack; nothing real fails. Keep the **Mac awake** (Docker Desktop pauses when it sleeps and the timings assume it does not) and budget **at most 3 sign-ins** (limit: 5 per account per 15 minutes, never cleared). Fixture: `.local/mvp01-owner/fixtures/invoice-002.eml`, SHA-256 `bc1865c1b375de7f34054102f95daea067d8c4ef619796dd8fab8b110f28f58c` (invoice `MVP01-2026-002`, 245.60 EUR, due date left Unknown; attachment SHA-256 `074f8e821ab5650b4f8b0136315a847c51998c8d40a6effe0995deb6b16c2102`, 140 bytes). `rebuild` installs it.

1. `bash scripts/mvp01-owner.sh rebuild`, sign in once, create a reminder a few minutes ahead (task and reminder control as in the first journey).
2. `bash scripts/mvp01-owner.sh outage on` — answer model stopped, destination cannot be asked and its next write times out (simulated). `status` shows `outage: ON`.
3. Calendar screen: mark the synthetic source offline. The overview says offline/stale with the last-good time and makes no free-day claim.
4. Ask a question: *Local model unavailable* (needs a reviewed document; with none you see "no sources"). Tasks, reminders, documents and import keep working; the reminder is delivered once.
5. Import `invoice-002.eml` twice, review, approve the plan only, then request the filing (two acknowledgements). It shows **Outcome not confirmed** with the plain reason; the Attention inbox lists it with *Open related document* (then *Load invoice review* to see the filing panel). History shows requested/attempted only; ledger effects stay unchanged.
6. `bash scripts/mvp01-owner.sh restart --kill`; sign in again: same waiting state; the model stays stopped (the outage is still on).
7. `bash scripts/mvp01-owner.sh outage off`: the filing becomes **Filed** with exactly one new ledger effect. While the destination was unreachable Butler asked it again only about every 15 minutes (the spec 069 back-off, unchanged), so after `outage off` this can take **up to about 16 minutes**; leave the page and look again later, or use Refresh (the panel stops polling by itself after about 2 minutes); import `invoice-002.eml` once more: replay. Mark the calendar online and import a fresh snapshot yourself; answers work again.

**Stated limit (S4):** if a destination answers lookups but its *writes* time out three times, the filing ends `failed` (final) although the destination was only unreachable. The composed outage avoids this because the destination cannot be asked either. Changing the write-only case needs a spec 069 change and is an owner option.

**Stated limit (S10):** a reminder is delivered in one database transaction. If the reminder worker is killed at the due time it appears **late** (at the next worker pass, within about a minute of the restart), **never twice** and never lost.

The live checker (`scripts/mvp01-owner-check.py outage-journey|outage-end|peer`) is agent evidence only; its peer step replaces the synthetic peer's password for one command and is meant for a disposable verify stack, not your rehearsal stack, unless you decide otherwise.

## Third journey: the paper invoice (spec 078)

Invoices arrive as **PDFs**, sometimes as a scan. Butler reads them locally with the real Poppler (text) and Tesseract (OCR) engines, on **synthetic** PDF bytes only; no model, no provider, no mailbox, nothing leaves your Mac. The filing destination is still the **simulated metadata ledger**: it records the PDF's hash, size and logical path, never the PDF itself. The rebuild adds the PDF worker (`pdf_worker`: no network, read-only, default Docker seccomp plus an in-process guard; **this is not verified confinement**). The first rebuild pulls base images and takes longer. Keep the **Mac awake**; budget **at most 3 sign-ins** (limit 5 per account per 15 minutes, never cleared).

Fixtures (synthetic, generated deterministically by `scripts/mvp01-owner-fixtures/paper_fixtures.py`, checksums checked before they are copied to `.local/mvp01-owner/fixtures/`):

| File | What it is | SHA-256 |
|---|---|---|
| `invoice-pdf.eml` | text PDF, invoice `MVP01-2026-003`, 312.80 EUR | `1a9da9a9540a78f1772af19550b5c92038e14c03b7077e0b6eb9fd298e416680` |
| `invoice-scan.eml` | image-only PDF (a scan), invoice `MVP01-2026-004`; the Total line is deliberately blurred | `8847cd9921927af49514285bef440bf0e65b333d3c08088376422a171f3a15af` |
| `invoice-pdf-offline.eml` | text PDF, invoice `MVP01-2026-005`, imported while the PDF worker is stopped | `8d481f484b5b76a8dcd1c146d177f35cf847dd7721e2d90b66bfd5aeb6ce56ec` |

1. `bash scripts/mvp01-owner.sh rebuild`. `status` shows `pdf worker : running`. Sign in once. Note the ledger counts in `status` (baseline).
2. Documents → *Import forwarded email…* → `invoice-pdf.eml`, twice: the second time says **Exact email already imported**. The list shows the badge **Text extracted**. Open the document, tick the copy-limits acknowledgement at the bottom, then click **View original pages**: up to the first 3 pages are drawn as images in this page (nothing is embedded, saved or downloaded, and no PDF script, link or form is run). Reading a PDF in the browser is **not verified confinement** and is not claimed to be safe; a damaged or too large PDF says "The original could not be shown here". The extraction section says what was read.
3. Import `invoice-scan.eml`. Badge: **No text found**; the extraction section says it looks like a scan and suggests **Run OCR (up to 2 pages)**. Click it, then read the warning: OCR is uncertain and **a line can be missing**: the blurred Total is likely absent from the text even though the status says *ready*. **No claim is made about OCR accuracy**; the result can differ on another machine. Compare the text with the original shown below it.
4. *Correct and review* (your attestation that you compared), *Load invoice review*, confirm only what you can see in the original and leave the Total **Unknown** (and the invoice number if it was misread). Read *Unknown is not zero*: Unknown stays Unknown and a filing with an Unknown total records no total. Suggest or enter a plan, approve **the plan only**, then request the synthetic filing (two acknowledgements): **Filed** once; open its history; `status` shows the ledger **+1 effect** per filed invoice (the ledger holds metadata, not the PDF).
5. `bash scripts/mvp01-owner.sh restart`, then `restart --kill` (the printed list now includes `pdf_worker`). Sign in only if asked. Same documents, extraction states, reviews and Filed status; the ledger counts do not change.
6. `bash scripts/mvp01-owner.sh pdf-worker stop`. Import `invoice-pdf-offline.eml`: the original is kept and the badge says **Extraction unavailable**; the section says the PDF reader is offline, the original is kept, and what to do. The buttons are locked until you tick *I started the PDF worker and want to try again*: **each attempt while the worker is offline adds a version of the document (quota: 50 per document) and needs a new review**, which is unchanged backend behaviour; the lock only prevents accidental clicks and never hides the state. `status` says the worker is STOPPED by you, and it stays stopped across `start`, `rebuild` and `restart` until:
7. `bash scripts/mvp01-owner.sh pdf-worker start`, tick the box, click **Re-extract PDF text**: ready, a new unreviewed version; review is required again. `bash scripts/mvp01-owner.sh stop` keeps your data.

**Stated limits.** Real Poppler/Tesseract on synthetic bytes; OCR accuracy is not claimed and one scan on one setup was observed. Seccomp: default Docker profile plus an in-process guard, not verified confinement for this stack. Filing is metadata-only; the PDF bytes live in the application database only. Restart evidence is container restart and SIGKILL of the application, workers and the PDF worker; no host reboot. A scan has at most 2 OCR pages; handwriting, photos, several attachments and HTML mail are not supported.

The live checker (`scripts/mvp01-owner-check.py paper-journey|paper-verify|paper-worker-down|paper-repaired|paper-peer|paper-hostile-import`) and the browser spec `frontend/e2e/mvp01-paper.spec.ts` are agent evidence only; they run on a disposable copy, not on your stack, and are not your acceptance.
