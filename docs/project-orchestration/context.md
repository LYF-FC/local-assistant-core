# Butler project context

This is stable orientation for a new orchestrator. The north star is **MVP-01: a coherent, usable end-to-end Butler user journey**. Prefer complete user-facing capabilities and meaningful vertical slices over isolated technical gate work. MVP gates constrain acceptance and define evidence; they are not a sequential project plan. Product status, current priorities, open PRs and the next task are intentionally omitted because they change and have authoritative homes elsewhere.

## Product and engineering shape

Butler (Local Assistant Core) is a local-first assistant for private and shared household and professional records. Persistent operational truth belongs in structured stores; models interpret, summarize, recommend, or propose within application-enforced permissions. Deterministic schedules, reminders, jobs, migrations, backups, permission checks, and failure states must remain useful when inference is unavailable.

The current engineering baseline is FastAPI, PostgreSQL, and React/TypeScript. Windmill is the preferred deterministic workflow orchestrator; Home Assistant owns deterministic physical-home automation. Accelerated/native workloads are separately reviewed; ordinary platform services remain portable. Read the constitution and architecture before design or implementation work.

The product retains an Everyday MVP and later household, care, connected-life, education/NOMAD, professional, creative, financial, and governed-platform scope. The [feature register](../FEATURE_REGISTER.md) preserves requirement IDs and scope. The [project master](../../PROJECT_MASTER.md) owns current status and approved priorities; the [roadmap](../../ROADMAP.md) is a sequencing view. The [MVP acceptance contract](../MVP_ACCEPTANCE.md) owns gate criteria. Reconcile these sources and relevant specs with live GitHub state before prioritizing; do not infer current work from this context.

## Durable constraints

- Use synthetic data in repository development. Never place private records, credentials, `.env`, runtime exports, or host-specific plans in Git.
- Keep application permissions explicit and enforced server-side; prompts and agent roles are not security boundaries.
- No silent cloud AI fallback. State any data flow out of the private environment.
- Treat external providers, private data, host operations, production startup, sending/writing, real credentials/keys, and release actions as separately gated. A coding task does not grant their authorization.
- Preserve auditability, migrations, history, restore behavior, current identity authority, and negative tests for security-sensitive behavior.
- Distinguish synthetic engineering from a real integration and in-process behavior from process-restart evidence.
- Do not claim verification or acceptance from implementation, tests, CI, or merge alone. Only the owner accepts a gate, naming environment and scope.
- Never merge automatically.

## Where durable detail lives

Use [README.md](../../README.md) for product entry points; [AGENTS.md](../../AGENTS.md) and the [constitution](../../.specify/memory/constitution.md) for binding engineering rules; [DECISIONS.md](../../DECISIONS.md) for explicit decisions; [ARCHITECTURE.md](../../ARCHITECTURE.md) for architecture; [SECURITY.md](../../SECURITY.md) for security boundaries; [OPERATIONS.md](../../OPERATIONS.md) for operational procedures; [PROJECT_MASTER.md](../../PROJECT_MASTER.md) for current scope/gates/status/priorities; [MVP_ACCEPTANCE.md](../MVP_ACCEPTANCE.md) for acceptance; and [FEATURE_REGISTER.md](../FEATURE_REGISTER.md) for requirements.

Feature-specific details live in the relevant numbered specification and linked contract. CI and validation rules live in [DEVELOPMENT.md](../DEVELOPMENT.md), [TESTING.md](../TESTING.md), [CI_COMPUTE.md](../CI_COMPUTE.md), and [REPOSITORY_ADMIN.md](../REPOSITORY_ADMIN.md). Read current versions; these links are navigation, not a replacement for the sources.
