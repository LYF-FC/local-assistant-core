# Butler session handoff

Copy this into a fresh ChatGPT or Claude session and fill in task-specific fields. Verify all live state when the new session starts; this is a transfer aid, not current project status.

**North star: MVP-01 — a coherent, usable end-to-end Butler user journey.** Identify a concrete user journey and coherent deliverable; do not simply pick the next gate. Prioritize complete user-facing capabilities and meaningful vertical slices. Gates are acceptance constraints and evidence, not a sequential project plan. Reconcile prioritization against existing `docs/MVP_ACCEPTANCE.md`, `docs/FEATURE_REGISTER.md`, `ROADMAP.md`, `PROJECT_MASTER.md`, relevant specs, and live GitHub `main`/PR/CI state. Do not copy unaudited gap analyses or invent current status. Preserve security and governance without perfection loops or documentation churn.

## Task and owner decisions

- Intended outcome:
- Concrete user capability and journey:
- Requirement/gate IDs and contracts:
- Smallest complete implementation:
- Acceptance evidence and owner-facing E2E experience:
- Approved scope and explicit exclusions:
- Owner decision/authorization already granted (link/evidence):
- Owner decision still required and why (if any):
- Work mode: read-only / local edits / other specifically authorized action:

## Agent assignments

For each role or specialist used, record one assignment. Add rows as needed; do not create or maintain a standing status registry here.

| Role/category | Agent or owner | Mandate and bounded question | Source material | Files/permissions | Independence or conflict limits | Deliverable and return format | Reuse/retirement condition |
|---|---|---|---|---|---|---|---|
| Project Orchestrator (standing) | ChatGPT |  |  |  | Final reconciliation; no owner decisions |  | Standing |
| Journey Architect (standing) |  |  |  |  | Recommends; does not approve scope | Journey brief and acceptance criteria | Standing |
| Lead Engineer (standing) | Claude |  |  |  | No self-approval; bounded implementation | Changed paths, decisions, evidence, limits | Standing |
| Independent Reviewer (standing) |  |  |  | Read-only review | Separate from implementer; no branch edits | Findings, coverage, gaps | Standing |
| E2E Validation Architect (standing) |  |  |  |  | Separate from implementation and journey design; owner accepts | Owner-facing steps, expected/observed results | Standing |
| Governance & Documentation Auditor (standing) |  |  |  |  | No duplicate authority or trackers | Policy/link/status findings | Standing |
| Reusable specialist (optional) |  |  |  |  |  |  | Reuse when useful; revalidate assignment |
| Temporary specialist (optional) |  |  |  |  |  |  | Retire after deliverable is incorporated |

ChatGPT or Claude may instantiate justified internal specialists. State the expertise gap that warrants each one, why standing roles do not cover it, the standing role it reports to, its inputs and outputs, its independence limits, and its expected lifetime. Name the lifecycle steps (1–9 in [instructions](instructions.md)) each assignment covers; steps 3 and 8 are the owner's, and verification (7) is never recorded as acceptance (8). The owner retains decisions on scope, priorities, acceptance, and gated actions; agent assignment does not grant external authorization.

## Read first

1. `docs/project-orchestration/README.md`
2. `docs/project-orchestration/context.md`
3. `docs/project-orchestration/instructions.md`
4. `AGENTS.md` and `.specify/memory/constitution.md`
5. `DECISIONS.md`, `PROJECT_MASTER.md`, `docs/FEATURE_REGISTER.md`, and `docs/MVP_ACCEPTANCE.md`
6. Relevant specification, feature contract, architecture/security/operations docs, and development/testing/CI policy

## Verify live before acting

- Confirm repository, checkout, branch, HEAD, clean/dirty state, remotes, and existing changes; preserve them.
- Read authoritative sources and compare with the live default branch. Do not mistake historical anchors, roadmap text, PR descriptions, or this handoff for current status.
- Check GitHub's default-branch SHA; relevant PR state, exact head/base revisions, draft/review/conversation state, current checks, and linked issues/spec state as relevant.
- Identify conflicting or missing evidence, stale local content, and owner-only decisions. Do not mutate the checkout to catch it up without authorization.

## Evidence and handoff

- Repository and remote:
- Dedicated branch (`work/<batch>/<role>-<purpose>`):
- Exact full base commit SHA:
- Exact full branch HEAD commit SHA:
- Commit SHA(s) and direct commit link(s):
- Changed paths (exact, complete list):
- Branch link and PR link/status (if applicable):

- Authoritative source paths and contracts:
- Live PR/issue/CI links and exact revisions:
- Local files/changes made:
- Commands and exact results (including not run/skipped checks):
- Independent review and findings:
- E2E validation design and steps, with expected/observed outcomes:
- Agent verification (Orchestrator and E2E Validation Architect) against agreed criteria:
- Owner acceptance decision (owner only; environment and scope; or still pending):
- Known limits/risks:
- Unresolved owner decisions or authorization:
- Recommended next action and its evidence:

The required report states what is complete, exact revision and paths, behavior and limitations, tests/CI with exact results, review findings, outstanding decisions, authorization still needed, and the next evidence-based recommendation. Update only existing authoritative records whose defined facts changed. Do not create a duplicate roadmap, decision log, batch tracker, active-PR list, or next-batch status.


## Fresh-session takeover test

Before relying on this package for a new handoff, test it in a fresh ChatGPT conversation with no access to the prior conversation. Provide only the current four orchestration files, repository access, and any task-specific handoff completed above. Ask the new session to independently state the repository and north star; identify the six standing roles and nine-step lifecycle, including that owner approval and acceptance remain owner-only and agent verification is separate; identify the permanent branch format and required Git evidence; locate current project authority and verify live GitHub state; summarize the assigned work and next evidence-based action without inventing missing status; and name the exact branch, base SHA, HEAD SHA, changed paths, commits, links, and validation evidence it can verify. The test passes only when the new session gives a source-grounded, internally consistent takeover, preserves the approved architecture and lifecycle, identifies missing evidence as missing, and creates no extra file, registry, PR tracker, or next-batch tracker. Record the prompt, response, and pass/fail outcome in the conversation used for the test; do not add a fifth project file or treat the test as owner acceptance.
