# Git-Native Authentication & Authorization — Architecture Remarks and Plan Update Instructions

## Purpose

This document captures the authentication, authorization, identity, role, and policy recommendations for the Agent Platform.

It is intended to be provided to **Antigravity / Codex** together with the current Agent Platform architecture plan.

The purpose is to have Antigravity:

1. Review the current security/identity architecture.
2. Compare it against the recommendations in this document.
3. Resolve inconsistencies in the existing ADRs.
4. Update the main architecture plan accordingly.
5. Preserve the requirement that the platform does **not** require a centralized authentication or authorization server.
6. Keep the architecture local-first and Git-native.
7. Avoid introducing unnecessary infrastructure or enterprise identity complexity at this stage.

This document is a **review and change proposal**, not an instruction to blindly implement every detail.

---

# 1. Core Architectural Position

The Agent Platform should remain:

- local-first,
- Git-native,
- serverless from the platform's perspective,
- capable of operating without a centralized authentication server,
- capable of operating without a centralized authorization database,
- usable for a single local developer without requiring network infrastructure.

The desired security model is:

```text
Cryptographic Git/SSH identity
              ↓
       Repository policy
              ↓
     Policy / authorization
              ↓
     Agent Platform enforcement
              ↓
       Git hook guardrails
```

The important architectural distinction is:

> **Git should be the durable source of identity references and authorization policy, while the Agent Platform should enforce that policy locally. Git hooks should provide additional repository-operation guardrails rather than being the sole security authority.**

This preserves the user's original requirement:

> **No custom authentication or authorization server is required for the core platform.**

---

# 2. Authentication and Authorization Must Be Distinguished

Do not treat authentication and authorization as the same problem.

## Authentication

Authentication answers:

> **Who is this actor?**

The preferred identity anchor is a cryptographic key rather than merely Git username/email metadata.

Possible identity sources include:

- SSH signing key
- GPG signing key
- another cryptographically verifiable signing identity supported by Git

The platform should associate an actor with a stable key identity/fingerprint.

Conceptually:

```text
Actor
├── actor_id
├── display_name
├── principal
└── cryptographic_identity
      └── key fingerprint
```

Git author name and email may be retained as human-readable metadata, but should not be treated as proof of identity.

---

## Authorization

Authorization answers:

> **What is this actor allowed to do?**

This should be derived from repository/project policy.

Conceptually:

```text
Verified Identity
       ↓
Principal
       ↓
Role Assignment
       ↓
Capabilities
       ↓
Policy Conditions
       ↓
Allow / Deny / Require Approval
```

This separation should be explicit in the main architecture.

---

# 3. Do Not State That "Git Alone Provides Authorization"

The current architecture should avoid an absolute statement such as:

> "Authorization and authentication rely entirely on Git."

That wording is too broad.

Git provides:

- cryptographic signing/verification facilities,
- commit identity metadata,
- repository history,
- branch/ref concepts,
- access through Git hosting systems,
- hooks and repository-level controls.

However, the Agent Platform will still need to evaluate application-level actions such as:

```text
Can this actor:
- start a workflow?
- approve a ChangeSet?
- apply a ChangeSet?
- modify policy?
- approve a learning?
- execute a privileged command?
- access a protected artifact?
- modify a workflow definition?
```

These are platform/domain authorization decisions.

Therefore:

> **Git supplies identity and durable policy material; the platform's Policy Engine makes and enforces authorization decisions.**

---

# 4. Initial Identity Model

For the first local version, keep identity deliberately simple.

Recommended initial deployment model:

```text
One local OS user
       +
Git identity
       +
Verified signing key
       +
Repository/project policy
```

There is no need to implement:

- user registration server,
- password database,
- OAuth service,
- enterprise IAM,
- centralized session database,
- remote authorization service.

The local operating-system account plus verified cryptographic Git identity can provide the initial actor context.

---

# 5. Future Identity Providers Must Remain an Extension Point

Even though external identity providers are intentionally deferred, the architecture should not make future support impossible.

Define an identity boundary such as:

```text
Identity / Actor Port
```

or an equivalent abstraction.

Initial implementation:

```text
LocalGitIdentityAdapter
```

Potential future implementations:

```text
OIDCIdentityAdapter
GitHubIdentityAdapter
GitLabIdentityAdapter
EnterpriseIdentityAdapter
```

These should be adapters around the same domain concept rather than forcing the core domain to depend on a specific identity provider.

The platform should therefore be designed for:

```text
Core Domain
     ↓
Identity Port
     ↓
Provider Adapter
```

not:

```text
Core Domain
     ↓
GitHub-specific logic
```

---

# 6. Repository-Defined Roles

The preferred model is for roles to be defined by project/repository policy.

A possible structure is:

```text
.agent/
├── config.yaml
├── policy.yaml
└── access/
    ├── roles.yaml
    └── principals.yaml
```

Example conceptual model:

```yaml
roles:
  viewer:
    capabilities:
      - project.read

  developer:
    capabilities:
      - project.read
      - workflow.execute
      - changeset.stage

  reviewer:
    capabilities:
      - project.read
      - change.review
      - change.approve

  architect:
    capabilities:
      - project.read
      - architecture.write
      - plan.approve
```

And:

```yaml
principals:
  - fingerprint: SHA256:...
    roles:
      - architect

  - fingerprint: SHA256:...
    roles:
      - developer
```

This is conceptual only. Antigravity should determine the final schema.

---

# 7. Roles Must Not Be Self-Authorizing

A critical security issue is:

```text
Developer
    ↓
edits roles.yaml
    ↓
makes self Administrator
```

Repository versioning alone does not prevent this.

Therefore security-sensitive authorization policy changes must have an authority model.

Recommended concept:

```text
Principal Key
    ↓
normal identity

Authority Key
    ↓
authorized policy administration
```

A designated trusted authority or set of authority identities should be able to authorize changes to:

- role assignments,
- protected policy,
- security configuration,
- high-risk capabilities.

For a single-developer local setup, the authority may simply be the user's trusted signing identity.

For a future team setup, designated authority keys can represent maintainers/security administrators.

---

# 8. Signed Authorization Policy

The strongest Git-native approach is to make the authorization policy itself verifiable.

Conceptually:

```text
policy.yaml
     ↓
 digest
     ↓
signed authorization record
     ↓
 Git commit
```

The platform should be able to determine:

1. Which policy version is active?
2. Who authorized the policy?
3. Whether the policy has been modified.
4. Whether the current policy is trusted.
5. Which role/capability mapping was used for a particular decision.

A complete cryptographic design can be deferred, but the architecture should reserve the concept of:

```text
Signed Policy
```

and:

```text
Policy Version / Digest
```

---

# 9. Git Hooks Are Enforcement Helpers, Not the Sole Root of Trust

Git hooks should absolutely remain part of the architecture.

However, their responsibility should be described precisely.

Recommended role:

> **Hooks reinforce and validate repository operations at Git boundaries.**

Examples:

### pre-commit

Potential checks:

- required signature,
- protected file changes,
- policy consistency,
- agent metadata consistency,
- prohibited file modifications.

### pre-push

Potential checks:

- branch/ref policy,
- signed commits,
- protected branch rules,
- policy validity,
- repository consistency.

### Important limitation

Client-side Git hooks can be bypassed or replaced by the user.

Therefore:

```text
Hook
≠
ultimate authorization authority
```

Instead:

```text
Signed Policy
       ↓
Policy Engine
       ↓
Platform Enforcement

Git Hooks
       ↓
Additional Git-operation Guardrails
```

This distinction should be captured explicitly in the ADR.

---

# 10. Remote Git Enforcement Is Separate From the Platform

The local platform should not require a server-based application.

However, when a project uses a shared remote Git repository, that Git service may provide authoritative repository controls such as:

- repository access permissions,
- protected branches,
- server-side Git hooks,
- push/ref restrictions,
- required signatures.

This is not the same thing as requiring a custom Agent Platform server.

The architecture should state that:

> **Remote Git hosting controls are optional infrastructure external to the core platform.**

The local platform must remain operational without them.

---

# 11. Recommended Security Architecture

Use this conceptual model:

```text
                         ┌──────────────────────────┐
                         │      Git Identity        │
                         │ SSH/GPG signing identity │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │ Identity Verification    │
                         │ fingerprint / trust      │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │ Repository Policy        │
                         │ roles + capabilities     │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │      Policy Engine       │
                         │                          │
                         │ filesystem               │
                         │ commands                 │
                         │ workflows                │
                         │ approvals                │
                         │ Git operations           │
                         └────────────┬─────────────┘
                                      │
                         ┌────────────┴─────────────┐
                         │                          │
                       ALLOW                  REQUIRE APPROVAL
                         │                          │
                         ▼                          ▼
                   Execute/Stage              Human approval
                         │                          │
                         └────────────┬─────────────┘
                                      ▼
                         ┌──────────────────────────┐
                         │ Git hooks / checks       │
                         │ repository guardrails    │
                         └──────────────────────────┘
```

This should become the conceptual security architecture.

---

# 12. Application Authorization Should Be Capability-Based

Avoid designing the security model solely around human-friendly role names.

Prefer:

```text
Role
  ↓
Capabilities
```

For example:

```text
viewer
    → project.read

developer
    → project.read
    → workflow.execute
    → changeset.stage

reviewer
    → project.read
    → change.review
    → change.approve

architect
    → architecture.write
    → plan.approve
```

The exact capabilities should be discovered from actual workflows.

This allows the platform to ask:

```text
Does this actor have capability:
    changeset.apply
```

rather than hard-coding role names throughout the core.

---

# 13. Approval Is Different From Authorization

This distinction should be explicit.

Authorization:

> Is this actor allowed to perform this kind of operation?

Approval:

> Has the required human decision been made for this specific operation?

Example:

```text
Developer
    ↓
authorized to create ChangeSet
    ↓
creates ChangeSet

ChangeSet
    ↓
requires reviewer approval
    ↓
Reviewer approves exact digest
    ↓
ChangeSet may be applied
```

Therefore model:

```text
Authorization
+
Approval
```

as separate concepts.

A person can be authorized to request a change without being authorized to approve it.

---

# 14. Approval Must Be Bound to the Exact ChangeSet

A critical invariant:

> Approval must apply to the exact proposed change being approved.

Conceptually:

```text
ChangeSet
├── change_id
├── content digest
├── base revision
├── proposed operation
└── metadata
```

Approval:

```text
Approval
├── actor
├── ChangeSet ID
├── ChangeSet digest
├── policy version
├── timestamp
└── signature/evidence
```

Then:

```text
ChangeSet changes
        ↓
 digest changes
        ↓
previous approval invalid
```

This is essential for secure human-in-the-loop behavior.

---

# 15. Protect Security-Critical Files

At minimum, consider protected paths such as:

```text
.agent/policy.*
.agent/access/*
.git/*
```

But the architecture should avoid a hard-coded permanent list.

Use policy-controlled protected resources.

For example:

```text
Policy
├── protected paths
├── protected branches
├── protected operations
└── protected configuration
```

The platform itself must not allow an ordinary agent proposal to change its own security boundaries.

---

# 16. Hooks Should Also Be Versioned and Managed Carefully

If the platform installs or manages Git hooks, the plan should define:

- how hooks are installed,
- whether hooks are project-local or template-based,
- how updates happen,
- how user-owned hooks are preserved,
- how multiple tools coexist,
- how the platform detects tampering,
- how hooks are restored,
- how hook installation is made reproducible.

Avoid blindly replacing existing hooks.

Prefer composition or explicit managed-hook sections where practical.

---

# 17. Local GUI Authentication

The local web GUI does not require a centralized identity server.

Recommended initial model:

```text
OS user
   +
local platform process
   +
verified local Git identity
   +
short-lived/local capability token if needed
```

The GUI should communicate with the local Control API.

Security-sensitive actions such as:

```text
Approve Plan
Apply ChangeSet
Change Policy
Approve Learning
```

must be validated by the core platform rather than trusted because the request came from the GUI.

The GUI is a client, not a trusted security boundary.

---

# 18. Do Not Put Secrets Into Git-Native Identity/Authorization Files

The Git-native approach must not become a mechanism for storing private secrets.

Never store:

- private SSH keys,
- private GPG keys,
- access tokens,
- API keys,
- passwords,
- session secrets,
- cloud credentials

inside repository policy.

Repository data may contain:

- public key fingerprints,
- public identities,
- roles,
- capabilities,
- policy,
- signatures,
- audit references.

Private credentials remain in the appropriate OS/user credential stores.

---

# 19. Recommended Actor Model

Add a first-class `Actor` concept to the domain model.

Conceptually:

```text
Actor
├── actor_id
├── display_name
├── principal
├── identity_type
├── cryptographic_identity
├── roles
└── capabilities
```

For the initial platform:

```text
LocalGitActor
```

is sufficient.

Future actor providers can map into the same model.

Agent-generated actions should also have an explicit actor identity:

```text
Human Actor
      ↓
requested operation
      ↓
Agent Actor
      ↓
proposed operation
```

This allows audit logs to distinguish:

> Who requested this?

from:

> Which agent executed/proposed this?

---

# 20. Agent Identity

The platform already proposes a dedicated Git identity for automated commits.

Keep this concept, but make it explicit that:

```text
Agent identity
≠
Human identity
```

A run should be able to record:

```text
requested_by: human
executed_by: agent
approved_by: human
committed_by: agent identity
```

For example:

```text
Run
├── requested_by
├── proposed_by
├── approved_by
└── committed_by
```

This creates strong auditability without requiring a centralized service.

---

# 21. Recommended Authorization Decision Flow

For every security-sensitive platform operation:

```text
Request
  ↓
Identify Actor
  ↓
Load trusted project policy
  ↓
Verify policy integrity
  ↓
Resolve roles
  ↓
Resolve capabilities
  ↓
Evaluate contextual policy
  ↓
Determine:
    DENY
    ALLOW
    REQUIRE APPROVAL
  ↓
If approved:
    execute through controlled capability
  ↓
Record decision in Run/Event history
```

The system should record the authorization context used for important operations.

For example:

```text
AuthorizationDecision
├── actor
├── operation
├── resource
├── policy_version
├── role(s)
├── capability
├── result
└── reason/evidence
```

This will greatly improve debugging and auditability.

---

# 22. Relationship With the Existing Policy Engine Proposal

This authentication/authorization model should integrate with the broader Policy Engine recommendation.

Do not create a separate isolated "RBAC engine."

Prefer:

```text
                 Policy Engine
                       │
        ┌──────────────┼───────────────┐
        │              │               │
    Identity       Capability       Context
        │              │               │
        └──────────────┼───────────────┘
                       ↓
              Authorization Decision
```

The same Policy Engine can eventually enforce:

- identity authorization,
- filesystem restrictions,
- command restrictions,
- workflow restrictions,
- approval requirements,
- Git restrictions,
- learning restrictions.

---

# 23. Recommended ADR Replacement

The existing security ADR should be revised from a statement equivalent to:

> "Git-Based Security, Permissions & Agent Identity"

toward:

# ADR — Git-Native Identity, Authorization & Policy

Recommended content:

### Decision

The Agent Platform will use a Git-native identity and authorization model for its initial local-first architecture.

- Human identities are anchored to cryptographically verifiable Git/SSH/GPG identities where supported.
- Project/repository policy defines principals, roles, capabilities, and protected operations.
- The Agent Platform Policy Engine evaluates and enforces authorization locally.
- Security-sensitive policy changes require authorization by designated trusted authority identities.
- Git hooks provide repository-operation guardrails but are not the sole security authority.
- No centralized authentication or authorization server is required for the initial architecture.
- External Git hosting controls remain optional and provide additional remote repository enforcement where applicable.
- Future identity providers can be introduced through an identity abstraction without changing core domain logic.

### Rationale

This preserves:

- local-first operation,
- Git-native governance,
- portability,
- auditability,
- repository-level versioning,
- offline capability,
- no mandatory application server,
- future extensibility.

---

# 24. Security Model for Single-User and Team Use

The architecture should support a progression such as:

## Local single-user

```text
OS identity
+
Git cryptographic identity
+
local policy
+
local Policy Engine
+
local hooks
```

## Team/shared Git repository

```text
Individual Git identities
+
signed project policy
+
local Policy Engine
+
review/approval process
+
remote Git repository protections
```

## Future enterprise

```text
Enterprise identity provider
+
mapped project identities
+
same core authorization concepts
+
remote Git controls
+
optional centralized operational services
```

The first two should not require the third.

---

# 25. What This Architecture Deliberately Avoids

Do not introduce the following merely to solve authentication/authorization:

- custom authentication server,
- custom authorization server,
- mandatory cloud database,
- central user database,
- mandatory SaaS identity provider,
- enterprise IAM dependency,
- custom password management,
- remote session infrastructure.

Those are future integration possibilities, not requirements of the core platform.

---

# 26. Important Limitation to Document Explicitly

The plan should clearly state:

> **A user who fully controls a local repository and operating environment can potentially bypass local client-side controls.**

Therefore:

```text
Local hooks
    = guardrails

Local Policy Engine
    = platform authorization enforcement

Signed policy
    = durable policy authority

Remote Git protections
    = authoritative shared-repository enforcement when available
```

This is not a reason to abandon the Git-native model.

It is simply an explicit trust-boundary definition.

---

# 27. Recommended Acceptance Criteria

The updated architecture should satisfy the following:

## Identity

- An actor can be identified without a centralized identity server.
- Cryptographic identity is distinguishable from commit author metadata.
- Agent identity is distinguishable from human identity.
- Identity is represented through an abstraction rather than provider-specific core code.

## Authorization

- Roles can be versioned with the project.
- Roles map to capabilities.
- Capability checks happen in the core platform.
- Policy changes cannot silently self-authorize.
- Sensitive operations can require approval.
- Authorization decisions can be audited.

## Git-native governance

- Policy is Git-versionable.
- Policy integrity can be verified.
- Hooks reinforce Git repository boundaries.
- Existing user hooks are not blindly overwritten.
- Remote Git protections can complement the local model.

## No server dependency

- A local user can use the platform fully offline.
- No application-level auth server is required.
- No centralized RBAC database is required.
- The GUI can authenticate/authorize through the local platform boundary.

## Safety

- Private keys and secrets never enter repository policy.
- Policy-controlled protected paths cannot be modified by an untrusted agent.
- Approval is bound to the exact ChangeSet/digest.
- LLM output cannot bypass the Policy Engine.

---

# 28. Instructions to Antigravity / Codex

Use this document together with the existing Agent Platform architecture plan.

Do not blindly replace the existing ADRs.

Instead:

1. Inspect the current authentication, authorization, Git, hook, policy, GUI, and audit sections.
2. Identify statements that are too broad or internally inconsistent.
3. Preserve the requirement for a serverless/local-first architecture.
4. Revise the security ADR around:
   - Git-native identity,
   - repository-defined authorization policy,
   - local Policy Engine enforcement,
   - Git hook guardrails,
   - optional remote Git enforcement.
5. Introduce an `Actor`/identity abstraction where appropriate.
6. Introduce capability-based authorization rather than hard-coding role names throughout the core.
7. Separate authorization from human approval.
8. Make ChangeSet approval cryptographically or digest-bound in the architecture.
9. Define trusted policy-authority semantics so users cannot self-elevate by simply editing role files.
10. Keep external identity providers as future adapters, not current dependencies.
11. Do not introduce a central authentication/authorization server.
12. Do not expand the product into an enterprise IAM system.
13. Ensure the GUI relies on the Control API and cannot bypass core authorization.
14. Integrate identity and authorization with the proposed Policy Engine.
15. Update relevant architecture diagrams and ADRs.
16. Update the architecture invariants and acceptance criteria as necessary.

## Important constraint

**Do not start production implementation as part of this review.**

This task is to update and reconcile the architecture plan.

After making the plan changes, report:

- Which security/identity sections were changed.
- Which ADRs were changed or added.
- Which recommendations were accepted.
- Which recommendations were rejected and why.
- What remains deferred.
- What trust boundaries now exist.
- Whether the resulting architecture still requires no central authentication/authorization server.
- Whether any new blocker or major feasibility issue was discovered.

---

# 29. Final Target Security Principle

The final architecture should aim for this model:

```text
         Git / Cryptographic Identity
                    │
                    ▼
          Signed Project Policy
                    │
                    ▼
             Policy Engine
                    │
           ┌────────┴─────────┐
           │                  │
       Authorization       Approval
           │                  │
           └────────┬─────────┘
                    ▼
            Controlled Action
                    │
                    ▼
         Staging / Validation
                    │
                    ▼
             Git Commit
                    │
                    ▼
          Hooks / Remote Git
           Guardrails
```

The key principle is:

> **The Agent Platform should be able to provide identity, authorization, approval, and auditability without requiring a custom centralized authentication or authorization server. Git should remain the durable governance and identity ecosystem, while the local platform provides the policy evaluation and enforcement needed for its own operations.**
