# Spec 077 plan

Constitution and dependency review: no migration, grant, trigger, rate-limit, clock, CORS or proxy-trust change; no new service or dependency; the simulated outage reuses the existing synthetic ledger controls and container stop; frontend changes are wording and one read-only status read.

Sequence: (1) characterise S4/S10 with disposable-PostgreSQL tests (done first; no behaviour change needed); (2) fixture F2; (3) `outage on|off`, `status`, restart persistence; (4) shared reason text in filing panel and inbox card, panel status read on mount, invoice-panel hint; (5) confirm the stopped answer service path; (6) checker `outage-journey`/`outage-end`/`peer`; (7) guide, decision and status records; (8) tests and live verification on a disposable verify stack (own project, ports and subnet; never another project).

Decision (R4): no auto-load of the invoice review on mount (accepted behaviour). The filing panel's own status read runs only when the panel appears. The inbox "Open related document" link remains the entry point.
