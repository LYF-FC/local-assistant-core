# Project orchestration takeover

This package helps a fresh ChatGPT session coordinate Butler work in `LYF-FC/local-assistant-core`. It is workflow guidance, not a new source of product scope, delivery status, priorities, decisions, or PR tracking.

**North star: MVP-01 — a coherent, usable end-to-end Butler user journey.** Prioritize complete user-facing capabilities and meaningful vertical slices over isolated technical gate work. Gates remain acceptance constraints and evidence, not a sequential project plan. Before choosing work, reconcile prioritization against the authoritative [MVP acceptance](../MVP_ACCEPTANCE.md), [feature register](../FEATURE_REGISTER.md), [roadmap](../../ROADMAP.md), [project master](../../PROJECT_MASTER.md), relevant specs, and live GitHub `main`/PR/CI state. Each proposed batch must state the user capability it delivers, related existing MVP requirements, the smallest complete implementation, and sufficient acceptance evidence. Preserve security and governance standards while avoiding perfection loops and documentation churn.

## Read in this order

1. [Stable project context](context.md)
2. [Durable instructions](instructions.md)
3. [Handoff template](handoff-template.md)
4. Repository instructions and authoritative sources below, then the relevant feature contract.

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

## Important boundaries

- Do not create a duplicate roadmap, decision log, batch tracker, active-PR list, or “next batch” status here.
- A branch, test pass, merged PR, independent verification, owner acceptance, live integration, and production readiness are distinct facts.
- GitHub state and checks change. Verify them live before selecting or handing off work. This package intentionally contains no current batch or PR status.
- No commit, push, PR creation, review submission, merge, release, private-data operation, live integration, or external action is authorized by this documentation package.
