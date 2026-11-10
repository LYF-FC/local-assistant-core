# Plan / analyze

Implement a small read-only operations module/router over existing authority and SELECT grants, without migration or business-state changes. SQL selects only caller-scoped job statuses with bounded LIMIT26, then appends metadata-only access audit and revalidates session before release. Runtime software inventory uses installed metadata rather than a checked-in version list; all approvals/licenses/advisories remain unassessed.

Implement an ephemeral technical-admin UI and strict typed adapter, with bounded job summaries, explicit unknowns and a visible freshness deadline. Reuse existing synthetic technical administrator and calendar browser phase; do not alter fixture ownership/authentication limits. Full conservative CI is selected by backend behavior; do not weaken its gate. Focused verification first, required checks once per coherent completed batch, full disposable PostgreSQL and focused trusted HTTPS/browser evidence. Keep private installation unchanged.

Constitution checklist: local deterministic processing; current authority/audit; no external effects/data access; no model dependency; no schema or recovery mutation; no implied health/approval/host acceptance. Spec does not supersede any MVP or deferred feature contract.

Authority reconciliation: inspection of runtime_role.py confirmed audit_events is INSERT-only. A direct audit query would fail under the real runtime role and weaken isolation if SELECT were added. Preserve that contract: expose audit review as unavailable, retaining OPS-10/reporting for a separately reviewed narrow projection. This supersedes only the draft activity-display approach, not the original feature requirement.
