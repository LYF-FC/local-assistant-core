# Butler Code — post-MVP scope and pilot boundaries

Owner-approved scope, 24 November 2026. This is a planning contract for a future supervised coding capability, not implementation authorization or a second status tracker. [PROJECT_MASTER.md](../PROJECT_MASTER.md#post-mvp-scope-addition--butler-code-owner-approved-24-november-2026) owns current planning/status; [the owner decision](../DECISIONS.md#24-november-2026--butler-code-post-mvp-scope-only) records the authorization. The existing [orchestration guidance](project-orchestration/instructions.md) continues to govern roles, independence and lifecycle.

## Specify: useful outcome and requirement mapping

Help a household member turn a small side-project issue into a reviewable, tested change and something they can personally try, while preserving the project's purpose, decisions and next steps. A project such as spotdl is an example only: no target repository, issue, account or source has been selected or authorized.

This names a workflow over retained WORK-07 project continuity, OPS-07 script catalogue, OPS-08 supervised software repairs and CORE-07 scoped coordination, using existing permission/audit/job foundations. It does not add a requirement ID, duplicate the backlog, expand CORE-07's MVP acceptance or imply those broad requirements are complete. Existing household, professional and later scope remains retained.

## Clarify: timing and unresolved choices

Begin only after an accepted Everyday MVP and a separately owner-approved pilot brief. Current MVP-01 journey delivery stays the focus; no current Claude agent is assigned Butler Code implementation or asked to interrupt that work. This scope approval does not assign a version/date or reorder existing post-MVP commitments.

The future brief must select the project, one issue, expected result, supported environment, licensed source and fixture data, permitted files/tools/network actions, resource/time limits and rollback. It must define model/runtime readiness and an explicit communication interface with external A1. These choices are unresolved. Hermes and model-switching research remain independent investigations, not prerequisites or selected dependencies. Implementation, model selection, benchmarking, human verification and owner acceptance remain pending.

## Roles: external A1 and bounded A2–A6 support

| Role | Future Butler Code responsibility | Authority and independence boundary |
|---|---|---|
| **A1 — Project Orchestrator - ChatGPT** | Remains the external coordinator: challenge the proposed brief, keep scope useful, inspect exact evidence, reconcile findings and send bounded correction/nudge requests through an explicitly supported interface. | Butler Code may prepare status and recommendations but does not replace A1 or make scope/acceptance decisions. No continuous background supervision, automatic wake-up or working interface is claimed by this document. |
| **A2 — Journey Architect** | Translate a project idea/issue into a concrete user flow, smallest useful change, constraints and observable acceptance criteria. | Proposes scope; the owner approves it. Does not make every attractive improvement part of the pilot. |
| **A3 — Lead Engineer** | Reproduce the issue, implement the approved change in an isolated branch/workspace and provide reproducible checks, diff and runnable demonstration. | No self-approval or independent verification of its own patch. No publication, deployment or access expansion follows from implementation authority. |
| **A4 — Independent Reviewer** | Independently inspect the exact diff, callers, tests and relevant security boundaries against the approved contract. Report actionable defects and evidence gaps. | Must not design/implement/edit the reviewed patch. Separate role names or model calls do not prove independence; inspect original evidence, not the implementer's conclusions. A different model is a comparison option, not an independence guarantee. |
| **A5 — E2E Validation Architect** | Design the owner-facing validation path before implementation, then independently exercise the delivered result at an identified revision and report expected/observed results, skips and limitations. | Separate from implementation. Component tests do not replace the continuous user journey; agent verification does not accept the owner's gate. |
| **A6 — Governance & Documentation Auditor** | Check permissions, data flows, accurate status language, required documentation and consistency with evidence. | Update existing authoritative project records only when facts change; no duplicate tracker or self-referential merge-fact PR loop. No scope expansion or acceptance authority. |

The owner retains substantive direction, scope, project/data access, consequential actions and personal acceptance. Support for A2–A6 can grow later; the pilot starts primarily with bounded A3 implementation plus independent A4/A5 support, and proportionate A2/A6 work. Six concurrent autonomous agents are not a requirement. Role automation must earn its complexity through evidence.

## Plan and tasks: smallest future pilot

1. Owner and external A1 select one small project issue and approve a bounded brief. Prefer a public/synthetic reproduction; do not introduce household/employer records or credentials.
2. A2/A1 define the concrete user outcome and exclusions; A5 independently prepares directly followable validation steps and failure cases.
3. A3 reproduces the issue on a known base, creates a minimal patch on an isolated branch and runs appropriate checks within the approved envelope.
4. A4 reviews the exact candidate revision independently. A3 resolves findings; changed code gets the necessary re-review and rechecks.
5. A1/A5 inspect the final revision and demonstrate the complete scenario, recording expected/observed results and gaps. The owner personally tries it and decides acceptance, naming revision, environment and scope.
6. A6 reconciles only the affected existing project records. Publication or deployment, if wanted, follows its own explicit authorization and does not follow automatically from acceptance.

This maps to the existing nine-step lifecycle rather than replacing it. No task above is started by this scope approval. A usable patch/demonstration is the pilot deliverable; a general IDE, plugin marketplace, autonomous project factory, multi-project scheduler and self-modifying agent platform are outside the pilot.

## Security, data and operational boundaries

- Use an isolated repository/worktree and sandboxed execution identity with only approved mounts/files, tools, network destinations and bounded commands. A branch is not an OS security boundary. Keep Butler application data and unrelated repositories inaccessible. No general production shell or Docker socket authority.
- Preserve FastAPI/PostgreSQL/React and application-enforced permissions. A model can propose operations, not grant capabilities. Repository content, issues, dependencies, build scripts and tool output are untrusted inputs, including instructions embedded in them.
- Development and validation use synthetic data only. No private family/employer source, private media, production credentials or live service access is authorized here. Keep project contexts, caches, logs and temporary artifacts separate from household/Work records and from other projects.
- Default to approved local inference. Nothing leaves the installation because of this document. Sending future source/context to external A1 or another provider requires an explicit reviewed data-flow contract and the applicable authorization; retaining ChatGPT as A1 is not blanket permission to export private code or data. Use only the minimum approved public/sanitized evidence.
- No implicit installs, weight downloads, benchmarks, dependency updates, cloud fallback, secret provisioning or security-control changes. Each future pilot brief must identify what it needs and satisfy the corresponding rights/resource/access checks.
- Record task, base/head, exact changed paths, source/fixture provenance, model/runtime/configuration versions when used, tool actions, check outcomes and unresolved failures. Keep implementation, commit, publication, merge, testing, independent review/verification, owner acceptance and deployment as separate facts.
- Commit/push/PR/merge/release, external messages, real writes/deletion, deployment and irreversible changes require explicit authorization for the named action. No autonomous self-upgrade, approval bypass or deployment follows from a successful test or accepted code review.
- Stop on out-of-scope work, missing rights, ambiguous side effects or exhausted limits; retain a clear partial result and manual recovery path. Model/worker failure must not disrupt Butler's deterministic tasks or records.

## Proposed pilot acceptance and later expansion

Before implementation, specify a reproducible failing case, expected corrected behavior, executable regression checks, supported environment, measurable time/resource envelope and owner-facing demonstration. Evaluate whether the result actually saves the owner effort, including review/rework time; do not judge success by agent count or generated lines.

Acceptance evidence must identify the final revision and include the reproduction, minimal diff, test commands/results/skips, independent findings and resolutions, a continuous runnable demonstration, denied cross-project/credential/network access, failure/cancellation cleanup and preservation of originals/unrelated work. Tool-control and permission changes need appropriate negative tests; no passing result is asserted here. The owner alone accepts the named scope after personal trial.

Only after the small pilot demonstrates value should the owner consider broader A2–A6 automation, multiple projects or additional models. A future feature spec/ADR must resolve the interface with A1, tool isolation, data retention/export/forgetting, update/rollback, model quality and resource budgets before implementation. This planning record completes documentation of the approved scope only; it certifies no runtime, provider, host or product acceptance.
