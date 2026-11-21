# Butler project orchestration

This package guides ChatGPT and Claude in coordinating work for Butler in `LYF-FC/local-assistant-core`. It defines the agent architecture and delivery process; it does not define product scope, project status, priorities, decisions, or PR tracking.

**North star: MVP-01 — a coherent, usable end-to-end Butler user journey.** Prefer complete user-facing capabilities and meaningful vertical slices. Keep security and governance standards while avoiding perfection loops and documentation churn.

## Start here

1. [Stable project context](context.md)
2. [Orchestration instructions](instructions.md)
3. [Session handoff template](handoff-template.md)
4. Follow repository instructions and reconcile authoritative project sources and live GitHub state before selecting work.

## Agent model

Six standing roles provide stable accountability: Project Orchestrator (ChatGPT), Journey Architect, Lead Engineer (Claude), Independent Reviewer, E2E Validation Architect, and Governance & Documentation Auditor. Roles are responsibilities, not a requirement to run six agents on every batch. The orchestrator and Claude may create justified reusable or temporary specialists under the rules in [instructions](instructions.md).

Every batch accounts for nine responsibilities in order: (1) journey discovery by the Journey Architect; (2) Orchestrator challenge and refinement; (3) owner approval of journey, scope, exclusions and authorisations; (4) E2E validation design; (5) implementation of the approved vertical slice; (6) independent review; (7) verification by the Orchestrator and E2E Validation Architect; (8) the owner personally trying the journey and deciding on acceptance; (9) governance and documentation reconciliation. Agent verification (7) and owner acceptance (8) are separate. Effort is proportionate to batch size and risk; not every batch needs every agent. Details are in [instructions](instructions.md).

## Sources of truth

| Subject | Authority | Rule |
|---|---|---|
| Foundational principles and constraints | [Constitution](../../.specify/memory/constitution.md) | Highest-level project constraints. |
| Owner-approved scope/direction decisions | [DECISIONS.md](../../DECISIONS.md) and approving PR evidence | Apply the latest explicit decision; reconcile the master as required. A proposal is not approval. |
| Current scope, MVP gates, delivery facts, priorities and sequencing | [PROJECT_MASTER.md](../../PROJECT_MASTER.md) | Single consolidated current project authority. Check its freshness and reconcile against live GitHub. |
| Requirement IDs and retained requirement text/evidence pointers | [Feature register](../FEATURE_REGISTER.md) | Do not remove or silently narrow scope. |
| Acceptance criteria and repeatable procedures | [MVP acceptance](../MVP_ACCEPTANCE.md) | Gates need their own evidence; only the owner accepts them. |
| Detailed feature behavior | Relevant `specs/NNN-*/` contract, plans/tasks/convergence when present, and linked feature contract | Use the contract selected by the master/register. |
| Architecture and operational/security procedures | [ARCHITECTURE.md](../../ARCHITECTURE.md), [SECURITY.md](../../SECURITY.md), [OPERATIONS.md](../../OPERATIONS.md), and topic-specific `docs/*.md` | Each owns its topic. |
| Engineering process and documentation governance | [AGENTS.md](../../AGENTS.md), [SPEC_KIT.md](../../SPEC_KIT.md), [DEVELOPMENT.md](../DEVELOPMENT.md), [TESTING.md](../TESTING.md), [CI_COMPUTE.md](../CI_COMPUTE.md), [REPOSITORY_ADMIN.md](../REPOSITORY_ADMIN.md) | Follow repo-local instructions and current CI policy. |
| Generated counts, overview and dashboard | [FEATURE_OVERVIEW.md](../FEATURE_OVERVIEW.md), `FEATURE_PROGRESS.json`, `FEATURE_DASHBOARD.html` | Derived/generated evidence only. Never hand-edit; update authoritative source and run the documented generator/check. |
| Historical narrative and sequencing views | [CONTEXT.md](../../CONTEXT.md), [ROADMAP.md](../../ROADMAP.md), [CHANGELOG.md](../../CHANGELOG.md), [BACKLOG_STATUS.md](../BACKLOG_STATUS.md), dated reports | Useful history/navigation, not current independent status or approval. |

When sources disagree, apply the precedence in `AGENTS.md` and `PROJECT_MASTER.md`; flag unresolved contradictions rather than choosing silently. Architecture and operational procedures retain authority over their own subjects.

## Authority and boundaries

The owner retains authority over approval, scope and priority decisions, acceptance, merge, release, and real-world activation. This package is workflow guidance only. See [stable context](context.md) and [durable instructions](instructions.md).

- Do not create a duplicate roadmap, decision log, batch tracker, active-PR list, or “next batch” status here.
- A branch, test pass, merged PR, independent verification, owner acceptance, live integration, and production readiness are distinct facts.
- GitHub state and checks change. Verify them live before selecting or handing off work. This package intentionally contains no current batch or PR status.
- No commit, push, PR creation, review submission, merge, release, private-data operation, live integration, or external action is authorized by this documentation package.
