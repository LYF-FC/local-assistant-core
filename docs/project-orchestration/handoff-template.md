# Butler session handoff

Copy this into a fresh ChatGPT or Claude session and fill in only the task-specific fields. Verify all live state when the new session starts; this note is a transfer aid, not current project status.

**North star: MVP-01 — a coherent, usable end-to-end Butler user journey.** Identify the highest-value user journey and propose a coherent deliverable; do not simply pick the next gate. Prioritize complete user-facing capabilities and meaningful vertical slices. Gates are acceptance constraints and evidence, not a sequential project plan. Reconcile any prioritization against existing `docs/MVP_ACCEPTANCE.md`, `docs/FEATURE_REGISTER.md`, `ROADMAP.md`, `PROJECT_MASTER.md`, relevant specs, and live GitHub `main`/PR/CI state. Do not copy unaudited gap analyses or invent current status. Maintain security/governance standards without perfection loops or documentation churn.

## Task

- Intended outcome:
- Highest-value user journey and why it matters now:
- Concrete user capability proposed:
- Requirement/gate IDs:
- Smallest complete implementation:
- Acceptance evidence tied to existing criteria:
- Approved scope and explicit exclusions:
- Decision or owner authorization already granted (link/evidence):
- Work mode: read-only / local edits / other specifically authorized action:

## Read first

1. `docs/project-orchestration/README.md`
2. `docs/project-orchestration/context.md`
3. `docs/project-orchestration/instructions.md`
4. `AGENTS.md` and `.specify/memory/constitution.md`
5. `DECISIONS.md`, `PROJECT_MASTER.md`, `docs/FEATURE_REGISTER.md`, and `docs/MVP_ACCEPTANCE.md`
6. Relevant specification, feature contract, architecture/security/operations docs, and development/testing/CI policy

## Verify live before acting

- Confirm repository, checkout, branch, HEAD, clean/dirty state, remotes, and existing changes; preserve them.
- Read the live default-branch versions of authoritative docs and compare with the checkout. Do not mistake historical anchors, roadmap text, PR descriptions, or this handoff for current status.
- Check GitHub's default-branch SHA; relevant open/closed PRs, exact head/base revisions, draft/review/conversation state, and current checks; linked issues and spec state as relevant.
- Identify conflicting or missing evidence, stale local content, and owner-only decisions. Do not mutate the checkout to catch it up without authorization.

## Relevant evidence and links

- Authoritative source paths:
- Feature contract/spec:
- Live PR/issue/CI links and exact revisions:
- Local files/changes made:
- Commands and results (include what was not run):
- Independent review and findings:
- Known limits/risks:

## Agent assignments

- ChatGPT orchestrator:
- Claude implementation agent/task (if used):
- Independent reviewer (separate from implementer):
- Optional research/test/docs role and bounded question:
- Files or areas each may edit:
- Return format and due/handoff condition:

Normally ChatGPT owns scope, live-state reconciliation, prioritization proposal, independent review, and final status. Claude owns the bounded implementation and implementation evidence. Add optional agents only for distinct separable work. Do not create overlapping editors or confuse model recommendations with owner decisions.

Every proposed batch identifies its concrete user capability, related existing MVP requirements, smallest complete implementation, and sufficient acceptance evidence. Treat gates as constraints/evidence rather than the project sequence. Preserve security and governance; update existing authoritative records only when their defined facts change.

## Required handoff report

State what is complete, exact revision/paths, behavior and limitations, tests/CI with exact results, review findings, outstanding questions/decisions, authorization still needed, and the next recommended action with its source evidence. Update only the existing authoritative records whose facts changed. Do not create a duplicate roadmap, decision log, batch tracker, active-PR list, or next-batch status.
