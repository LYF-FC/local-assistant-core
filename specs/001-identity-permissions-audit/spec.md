# Feature Specification: Identity, Permissions, and Audit Foundation

**Feature Directory**: `001-identity-permissions-audit`  
**Created**: 2026-10-26  
**Status**: Development foundation delivered; broader future-domain/host/production acceptance remains open
**Input**: Establish Butler's first enforceable identity, authorization, approval, and audit foundation.

## User Scenarios & Testing

### User Story 1 - Authenticated Family Identity (Priority: P1)

As a household user, I need Butler to know which authenticated person is making a request so that
private and shared information is never mixed accidentally.

**Why this priority**: Every later Butler feature depends on trustworthy identity.

**Independent Test**: Two test users can authenticate separately and receive distinct identities; an
unauthenticated request to a protected endpoint is rejected.

**Acceptance Scenarios**

1. **Given** a protected Butler endpoint, **When** no valid authenticated session is present,
   **Then** access is denied and no protected data is returned.
2. **Given** two active users, **When** each authenticates, **Then** Butler resolves the correct
   identity for each request.
3. **Given** a disabled user, **When** that identity attempts to authenticate or reuse a session,
   **Then** protected access is denied.

### User Story 2 - Scope-Enforced Access (Priority: P1)

As a family member, I need Butler to enforce data scopes so that I only see or modify information I am
authorized to access.

**Why this priority**: Prompt-level separation is insufficient for private health, finance, business,
and child data.

**Independent Test**: A user with `household_shared` but without `finance_private` can access a
shared test resource and is denied a finance-private test resource.

**Acceptance Scenarios**

1. **Given** a user with an allowed scope, **When** the user accesses a resource protected by that
   scope, **Then** access succeeds.
2. **Given** a user without the required scope, **When** the user attempts the same access,
   **Then** access is denied and the denial is auditable.
3. **Given** a user has multiple scopes, **When** accessing each permitted domain,
   **Then** each authorization decision is evaluated from structured permissions rather than AI output.

### User Story 3 - Reconstructable Audit History (Priority: P1)

As an administrator, I need every meaningful protected action to produce an immutable audit event so
that I can reconstruct what happened and why.

**Why this priority**: Auditability is a constitutional requirement and a prerequisite for trusted
automation.

**Independent Test**: Execute a protected read, an allowed write, and a denied write; the resulting
audit records identify actor, scope, action, result, time, and affected entity where applicable.

**Acceptance Scenarios**

1. **Given** a meaningful state-changing action, **When** it completes, **Then** an audit event records
   the actor, action, scope, result, time, and relevant before/after context.
2. **Given** a permission denial, **When** access is rejected, **Then** the denial is represented in
   security/audit history without exposing protected content.
3. **Given** an AI-assisted action later uses a model, **When** the model materially contributes,
   **Then** the audit model supports recording model/runtime/version.

### User Story 4 - Explicit Approval for Consequential Actions (Priority: P2)

As a family user, I need consequential actions to wait for explicit approval so that Butler cannot
silently execute high-impact changes.

**Why this priority**: Approval is required before Butler can safely expand beyond read-only guidance.

**Independent Test**: Create a test action requiring approval, verify it cannot execute while pending,
approve it as an authorized user, and verify state transition history is preserved.

**Acceptance Scenarios**

1. **Given** an action marked approval-required, **When** it is requested, **Then** it remains pending
   and cannot be treated as completed.
2. **Given** an authorized approver, **When** approval is granted or rejected, **Then** the decision,
   approver, timestamp, and request context are preserved.
3. **Given** a stale or already-resolved approval, **When** another resolution is attempted,
   **Then** the system rejects the invalid transition.

### Edge Cases

- A session references a user that has since been disabled.
- A scope is removed while a session is active.
- The database is reachable but audit persistence fails during a protected write.
- Two approval decisions arrive concurrently.
- A protected write succeeds at the domain layer but audit persistence cannot be confirmed.
- A malformed or unknown scope key is supplied.
- A user attempts to grant themselves a scope they do not have authority to administer.

## Requirements

### Functional Requirements

- **FR-001**: Butler MUST authenticate protected API requests and resolve one structured active user.
- **FR-002**: Butler MUST support the canonical scopes `household_shared`, `member_a_private`,
  `member_b_private`, `parents_child`, `member_business`, `finance_private`, and
  `technical_admin`.
- **FR-003**: Authorization MUST be enforced in application code and MUST NOT depend on LLM output.
- **FR-004**: Protected resources MUST declare the scope or permission required for access.
- **FR-005**: Permission denials MUST return a deterministic denial without protected payload leakage.
- **FR-006**: Meaningful protected writes MUST create audit events containing actor, scope, action,
  timestamp, result, and affected entity identifiers.
- **FR-007**: Audit events MUST support source/context, before/after values, task/approval links, and
  model/runtime metadata where applicable.
- **FR-008**: Audit history MUST be append-only through normal application interfaces.
- **FR-009**: Approval-required actions MUST have explicit pending, approved, rejected, cancelled, and
  expired/stale handling as appropriate.
- **FR-010**: Approval resolution MUST record the approver and timestamp.
- **FR-011**: Invalid approval state transitions MUST be rejected deterministically.
- **FR-012**: User disablement and scope changes MUST take effect without relying on a new LLM session.
- **FR-013**: Authentication secrets/tokens MUST NOT be stored in Git.
- **FR-014**: Tests MUST cover authentication rejection, allowed scope access, denied scope access,
  audit creation, and approval state transitions.
- **FR-015**: The implementation MUST define failure behavior for a state-changing operation when the
  required audit record cannot be durably persisted.
- **FR-016**: The feature MUST remain functional when local AI inference is unavailable.

### Key Entities

- **User**: Human Butler identity with stable ID, display identity, active/disabled state, and timestamps.
- **Scope**: Canonical named authorization boundary.
- **UserScope**: Assignment of a scope to a user.
- **Session/Credential**: Authenticated session or credential linked to one active user.
- **AuditEvent**: Append-only record of a meaningful event, decision, denial, or state change.
- **Approval**: Request for human authorization of a consequential action.
- **Task/Action**: Structured operation that may link to approvals and audit events.

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100% of protected endpoint tests reject unauthenticated access.
- **SC-002**: 100% of tested cross-scope access attempts are denied without protected content leakage.
- **SC-003**: Every tested meaningful protected write has a corresponding reconstructable audit event.
- **SC-004**: Approval-required test actions cannot reach a completed/executed state before approval.
- **SC-005**: Disabling a user or removing a scope prevents subsequent protected access without restart.
- **SC-006**: The identity/permission/audit test suite passes with the local LLM service stopped.
- **SC-007**: A developer can query audit history for a test action and identify who acted, what was
  attempted, the outcome, when it happened, and which scope governed it.

## Assumptions

- Initial household user count is very small, but permission design must not hard-code exactly two users.
- Real family/private data is not required to implement or test this feature.
- The current PostgreSQL schema is an initial foundation and may be migrated as this feature is planned.
- Authentication mechanism details are intentionally left for the planning/clarification stage.
- Scope administration will initially be limited to a trusted technical/admin path.
- This feature does not yet implement Inventory, Health, Finance, child Care, or business records;
  it creates the enforceable security foundation those domains will use.

## Out of Scope

- Social login or public account signup.
- Internet-facing account recovery.
- Fine-grained domain-specific permissions beyond the canonical scope foundation.
- Production finance, health, care, or business data.
- Autonomous external actions.

