# MVP-01 owner rehearsal (Mac-local, synthetic) — spec 076

A named, disposable, single-stack Docker rehearsal on your Mac for the synthetic invoice journey. Contract and limits: [spec 076](../specs/076-mvp01-synthetic-invoice-journey/spec.md). Everything is synthetic and loopback-only; it is **not** acceptance, not a real integration and not production.

## Commands

```bash
bash scripts/mvp01-owner.sh start       # create private config, build images, start, seed the fixture, print the guide
bash scripts/mvp01-owner.sh status      # revisions, services, fixture checksum, CA fingerprint, identity, ledger counts
bash scripts/mvp01-owner.sh rebuild     # rebuild images from this checkout and recreate containers (data preserved)
bash scripts/mvp01-owner.sh restart     # container restart of api/web/caddy/workers/simulated model
bash scripts/mvp01-owner.sh restart --kill   # SIGKILL of api/workers/simulated model, then start again
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
5. In *My reminders* open your preferences and enable in-app reminders (opt-in; the worker ignores everyone else). Then schedule an in-app reminder on the task a couple of minutes ahead. The reminder worker (30 s cycle) delivers it once; acknowledge it; the task stays open.
6. Invoice review: prepare candidates, confirm issuer, number, issue date, total, currency, leave **Due date Unknown**, save; suggest the filing plan and approve it *as a plan only*. Nothing has been filed.
7. In *Synthetic filing execution*, read the bindings (document, source revision, plan revision, path, SHA-256, metadata-simulation limit), tick both acknowledgements and request the filing. It goes Pending → Filed (the worker cycles every 5 s). Open its history.
8. `restart`, then `restart --kill`. Sign in again: same records, review, plan, history, status **Filed**, one filing, and `status` shows ledger `effects: 1`.

Optional failure rehearsals before step 7 (`scenario`): `timeout-after-effect on` (effect lands, worker sees a timeout → *unknown* → reconciled to Filed with one effect), `timeout-before-effect on` (timeout without effect → conclusive absence → one retry), `lookup-unavailable on` (stays *unknown*, never retried blindly; `off` to resolve).

## Evidence labels

Process kill, container restart, host reboot and clean-host recovery are different things. `restart` is a container restart; `restart --kill` is a SIGKILL of the application/worker processes with PostgreSQL left running; a host reboot and a clean-host recovery are **not** exercised. Real-process SIGKILL tests against disposable PostgreSQL are in `backend/tests/integration/test_mvp01_journey_postgres.py`. The same journey can be checked through the API with `scripts/mvp01-owner-check.py` (see the script header); both are agent evidence, not owner acceptance.

## Stop and reset

`stop` keeps everything. `reset` also works when the generated config is gone (for example after deleting `.local/`) while the project's volumes remain: it then identifies the project by its exact Compose label and name prefix. It deletes, after you type the exact project name, only the containers, network and volumes carrying the `local-assistant-core-mvp01-owner` Compose label and prefix (verified before deletion) and `.local/mvp01-owner/`. It refuses to run if the generated config does not name the exact rehearsal database and synthetic marker. No prune, no other project, no images. Remove the old CA fingerprint from your keychain yourself.
