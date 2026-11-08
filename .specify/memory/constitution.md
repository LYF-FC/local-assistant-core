# Butler Constitution

## Core Principles

### I. Local-First Privacy and Data Sovereignty

Butler MUST keep persistent family context, operational records, private AI context, health data,
financial data, care records, and other sensitive household data under local control.

- Silent cloud AI fallback is prohibited. Local processing remains the default.
- A future external-model gateway MAY process a minimum payload only under explicitly user-validated rules, scoped permissions, data classification, payload-bound approval, provider-retention checks, budgets and local audit.
- Authorization to investigate/design this gateway is NOT authorization to send personal data. v0.1 ships without outbound AI capability; protected sensitive categories remain blocked by default.
- Family memory, authoritative records and credentials MUST NOT be exported as general remote-model context.
- Internet access MUST be capability-scoped and used only for an explicit integration or research need.
- GitHub MUST contain code, non-sensitive configuration, architecture, and specifications only.
- Production family records, raw mailbox content, credentials, invoices, health records, finance records,
  and private Butler memory MUST NOT be committed.
- Every new feature MUST state what data leaves the private environment, if any.

Rationale: privacy is an architectural property, not a prompt instruction.

### II. Structured State Is Authoritative

Operational truth MUST live in deterministic structured stores and MUST NOT depend on LLM memory.

This applies to:
- users and permissions;
- tasks and reminders;
- approvals;
- inventory and stock;
- health observations;
- finance balances and transactions;
- child care records;
- maintenance status;
- execution status;
- audit events.

AI MAY interpret, summarize, recommend, or propose changes, but MUST NOT silently replace structured
authority.

Rationale: the system must remain understandable, recoverable, and correct when AI is unavailable.

### III. Explicit Permissions and Human Control

Every read, write, external action, and sensitive tool MUST be governed by explicit application-level
permissions.

Initial scopes:
- household_shared
- member_a_private
- member_b_private
- parents_child
- member_business
- finance_private
- technical_admin

Consequential actions MUST require configured human approval. Butler MUST NOT autonomously:
- execute investments or transfers;
- enter subscriptions or legal commitments;
- make medical decisions;
- send high-impact external communications without the configured approval policy.

Prompt instructions alone MUST NEVER be treated as an authorization boundary.

Rationale: capability boundaries must remain enforceable even when models behave unexpectedly.

### IV. Auditability Is Non-Negotiable

Every meaningful state change, recommendation, approval, sensitive access, and external action MUST be
reconstructable.

Audit events MUST record where applicable:
- initiator;
- specialist/worker;
- task/request identifier;
- timestamp and environment;
- source/context used;
- tools/actions;
- before/after values;
- approval requirement and approver;
- outcome;
- model/runtime/version where AI materially contributed.

Corrections MUST preserve history rather than destructively erasing prior events.

Operational logs and governance/audit logs MUST remain distinct.

Rationale: Butler must be able to explain what happened, why, by whom, and with what evidence.

### V. Deterministic Core, AI as a Replaceable Capability

Schedules, reminders, recurring jobs, migrations, backups, permission checks, validation, device rules,
and other deterministic functions MUST continue working when the LLM is unavailable.

AI providers, models, and agent runtimes MUST be replaceable behind stable application interfaces.

Rationale: Butler is a family operating system, not a thin wrapper around a particular model.

### VI. Native for Accelerated Compute, Containers for Platform Services

A workload that materially benefits from Apple Silicon, Metal, MLX, native audio/video acceleration, or
direct macOS hardware integration SHOULD run natively on the Butler Mac.

Ordinary platform services SHOULD default to portable Docker containers.

Current examples:
- native: Ollama, MLX/llama.cpp candidates, Phonon TTS, future accelerated STT/vision;
- containers: PostgreSQL, FastAPI, React runtime, Windmill, Caddy, observability and ordinary workers.

Compose definitions MUST remain portable to a standard Linux Docker Engine.

Rationale: use Apple Silicon where it matters without sacrificing deployment portability.

### VII. Data Integrity, Migration Safety, and Portability

Every schema change MUST have an explicit migration path.

Critical data MUST be exportable in documented, human-inspectable formats where practical:
- JSON / JSONL;
- Markdown;
- original attachments;
- Excel where it materially improves human review.

Exports MUST preserve stable IDs, provenance, timestamps, corrections, and schema versions.

Backups are incomplete until restore is periodically tested.

Rationale: Butler must survive software changes, hardware loss, and future architectural replacement.

### VIII. Test-Backed, Incremental Delivery

Behavioral changes MUST have an objective verification path.

For security, permissions, audit, migrations, care, finance, health, and other high-risk domains,
automated tests are mandatory before a feature is considered complete.

Features SHOULD be delivered as bounded, independently testable increments.

Spec Kit convergence MUST report the agreed feature complete before it is treated as delivered.

Rationale: small verified increments reduce the risk of a large long-lived system drifting from intent.

## Architecture and Domain Constraints

- FastAPI + PostgreSQL + React/TypeScript is the current application baseline.
- Windmill is the preferred deterministic workflow orchestrator.
- Home Assistant owns deterministic physical-home automation.
- NOMAD is a separate hardware subsystem; Butler accesses it through constrained interfaces.
- Synology is the durable document/backup/archive layer, not the live PostgreSQL filesystem.
- business business data is isolated from unrelated family-private scopes.
- Phonon multilingual TTS is household/non-commercial only and MUST NOT be used for business or
  commercial output.
- Finance capability is analysis/recommendation only.
- Health and care features MUST distinguish unknown from negative/not-done states.
- Child-facing capabilities must use configured language preferences; no child profile is shipped.

## Development Workflow and Quality Gates

For meaningful features use the full Spec Kit flow:

1. specify
2. clarify
3. plan
4. checklist
5. tasks
6. analyze
7. implement
8. converge

Smaller low-risk changes MAY use the shorter specify -> plan -> tasks -> implement -> converge flow.

Before implementation:
- the feature MUST have explicit user outcomes and scope;
- constitution conflicts MUST be resolved or explicitly justified;
- data and permission impact MUST be identified;
- migration, export, backup, and audit implications MUST be addressed where relevant.

Before completion:
- required tests MUST pass;
- migrations MUST be exercised;
- sensitive data MUST be absent from Git;
- documentation MUST be updated when architecture or durable behavior changed;
- Spec Kit convergence MUST be satisfied.

Project-level truth remains:
- CONTEXT.md
- ROADMAP.md
- ARCHITECTURE.md
- DECISIONS.md
- OPERATIONS.md
- SETUP.md

Feature-level Spec Kit artifacts MUST NOT silently contradict those files. If a feature changes a durable
project decision, the canonical project documentation MUST be updated in the same delivery.

## Governance

This constitution governs all Butler feature specifications, plans, tasks, and implementation work.

Amendments require:
- an explicit rationale;
- a version change;
- review of affected project-level documentation and templates.

Versioning:
- MAJOR: incompatible governance/principle change;
- MINOR: new principle or materially expanded governance;
- PATCH: clarification without semantic change.

Compliance MUST be checked during feature planning and convergence.

### Amendment 2.0.0 — 2026-11-01

Rationale: the owner explicitly requested investigation of optional major-model API delegation under strictly validated rules. This narrows the previous categorical prohibition through an explicit, disabled-by-default exception. It does not activate a provider or grant data-transfer permission.

Affected documents reviewed: CONTEXT, ROADMAP, ARCHITECTURE, DECISIONS, OPERATIONS, SETUP, SPEC_KIT, spec 001 and new SCOPE/SECURITY/MEMORY/readiness documentation. No generated Spec Kit templates currently exist in this repository. Existing Windmill/Home Assistant and scope boundaries remain authoritative.

Version: 2.0.0 | Ratified: 2026-10-26 | Last Amended: 2026-11-01


Public-source projection: identifiers and names are generalized for fresh installations. Private historical governance/acceptance evidence is not exported or reclassified as new public evidence.
