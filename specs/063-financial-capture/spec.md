# 063 — Restricted manual financial capture contract

## Specify / clarify

Define the next existing MVP FIN-06 slice before implementation: owner-private finance goals, assumptions, recorded plans and sources with dated provenance, explicit confirmed/assumption/forecast/unknown basis, correction/history/export/forget and no financial action. See [the detailed contract](../../docs/FINANCIAL_CAPTURE.md). This batch delivers design, not executable finance storage/UI or full FIN-06 acceptance.

Use a dedicated server-validated record/revision boundary rather than a client-only convention in generic Memory. Reuse current identity/grants/audit/transport; no model/provider/automatic context projection. Existing finance_private is owner-private, not shared merely because both users hold the scope. Recorded acceptance of a plan is not execution approval and resets on material correction.

## Checklist / acceptance for this design batch

- Retain original FIN-06 goals/lifestyle/horizon/spending/property/constraints/source outcomes and later finance dependencies; preserve all155 references and original99 milestones/statuses; four already-partial rows may gain verified PR17 evidence without changing acceptance.
- Specify numerical bounds, strict unknown/decimal/date semantics, ownership/current authority, plan acknowledgement reset, quotas/history, no-op/conflict handling, export/forget/backup limits and migration-loss disclosure.
- Define actual PostgreSQL/concurrency/negative permission/audit/restore and trusted HTTPS evidence required before implementation is accepted. No runtime pass is inferred from design.
- Reconcile canonical scope/roadmap/architecture/decisions/operations/setup; check privacy/links/policy. No source data, real integration, migration, deployment, dependency or CI policy changes.
- One coherent commit/push/draftPR; documentation-only scope/final gate expected, other jobs intentionally skipped. No polling/merge/feature continuation after publication.
