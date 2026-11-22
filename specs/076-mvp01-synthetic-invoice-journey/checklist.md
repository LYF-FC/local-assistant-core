# Spec 076 review checklist

Entries are unchecked: this is a reviewer aid, not owner acceptance or independent verification.

- [ ] Plan approval still says `execution_authorized: false`; only a separate exact request starts work; two acknowledgements required in UI and API.
- [ ] Client never retries a conflict and validates owner/scope/document/revision/state/history order; no server text is rendered.
- [ ] Worker default unchanged (`memory`); `durable` is explicit and refuses unmarked/linked/relative/production targets.
- [ ] Ledger entries hold key/path/SHA-256/size only; never original or email bytes; never overwritten; control files only in a marked ledger.
- [ ] No migration, grant, trigger, rate-limit, clock, CORS or proxy-trust change; fixed subnet and Caddy address kept.
- [ ] Rehearsal mounts: Caddyfile (ro), simulated model script (ro), named volumes only; no `.env`, credentials, repository or home mount.
- [ ] Script: hidden prompt, 0600 config, distinct credentials, public CA only, no trust-store change, reset guarded and unpruned.
- [ ] Status vocabulary: implementation/integration/testing/verification/acceptance kept separate; nothing merged or accepted.
- [ ] Limits stated: metadata simulation, simulated model/calendar, no host-reboot or clean-host claim.
