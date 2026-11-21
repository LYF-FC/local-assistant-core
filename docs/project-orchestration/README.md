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

Every batch follows an adaptive lifecycle: orient and reconcile; investigate and recommend a concrete journey; obtain owner decisions where needed; plan and implement a bounded vertical slice; independently review; validate the complete journey with owner-facing evidence; reconcile durable documentation; and report outcome and remaining gaps. Adapt or omit steps only when the instructions permit.

## Authority and boundaries

The owner retains authority over approval, scope and priority decisions, acceptance, and real-world activation. This package is workflow guidance only. It creates no duplicate roadmap, decision log, tracker, current batch status, or authorization for external effects. See [stable context](context.md) and [durable instructions](instructions.md).
