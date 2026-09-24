# Agent Platform — Final Pre-Implementation Remarks for Antigravity

## Purpose

This is the final focused review of the current reconciled Agent Platform architecture plan.

The architecture is now strong enough to proceed toward implementation. The purpose of this document is **not** to reopen the architecture, expand the scope, or introduce another major redesign.

It identifies a small number of remaining issues where the current plan contains:

- technically inaccurate terminology,
- security semantics that should be made more precise,
- a few operational ambiguities,
- or guarantees that should be weakened to match what the implementation can actually prove.

After these points are reconciled, the architecture should be considered stable enough to move into implementation and test-driven validation.

---

# 1. Overall Assessment

## Recommendation

**Proceed with implementation after one final targeted reconciliation pass.**

The overall architecture is coherent:

```text
Local-first
+
Git-native governance
+
Headless core
+
Policy Engine
+
Capability-based authorization
+
Controlled ChangeSets
+
Human approval
+
Staging/verification
+
Run/Event persistence
+
Decoupled GUI
+
Additive workflow modules
```

The plan has successfully preserved project neutrality and avoided drifting back into an enterprise ALM/IDE/cloud-platform architecture.

Do not reopen those decisions.

---

# 2. P0 — Correct the ChangeSet Hashing Specification

## Current wording

The ChangeSet model currently describes per-file content digests using:

> RFC 8785 JSON SHA-256 hashes.

RFC 8785 is a canonicalization standard for JSON data. It should not be used as the hashing model for arbitrary source-file byte content.

## Recommendation

Separate:

### File-content hashing

Use a clearly defined canonical byte representation of file content and hash it with SHA-256 or another selected cryptographic hash.

Conceptually:

```text
File Content
    ↓
Canonical Byte Representation
    ↓
SHA-256
    ↓
File Content Digest
```

The canonical representation must define behavior for:

- UTF-8/text encoding,
- line endings,
- binary files,
- file modes,
- symlinks,
- empty files,
- deletes,
- renames,
- path normalization.

### Structured metadata hashing

RFC 8785 may be used for canonicalizing JSON metadata if desired:

```text
ChangeSet Metadata JSON
    ↓
RFC 8785 canonicalization
    ↓
SHA-256
```

Do not describe RFC 8785 as the content-hashing mechanism for arbitrary project files.

## Required plan change

Replace the current wording with an implementation-neutral canonical file-content hashing specification.

The exact canonical serialization can be finalized during implementation, but the distinction must be explicit in the architecture.

---

# 3. P0 — Do Not Claim "Atomic Apply" Without Defining What Atomic Means

The current plan still uses language such as:

> "atomically patched into target working tree"

and describes backups/rollback.

For a multi-file filesystem mutation, literal transactional atomicity is difficult to guarantee across arbitrary filesystems and operating systems.

## Recommendation

Use terminology such as:

> **transaction-like controlled apply with preflight, verification, rollback attempt, and explicit recovery state**

Recommended lifecycle:

```text
Preflight
   ↓
Verify target state
   ↓
Verify ChangeSet/security chain
   ↓
Prepare rollback data
   ↓
Apply
   ↓
Verify postconditions
   ↓
Success
   OR
Rollback attempt
   ↓
Verify restored state
   ↓
RecoveryRequired if uncertain
```

The architecture already contains `RecoveryRequired`; preserve it as a real safety state.

Do not promise universal rollback success.

---

# 4. P0 — Tighten the Trust-Binding Claim

The current Authority Key trust model is much better and now includes:

```text
~/.agent-platform/trust/<project-id>.json
```

plus repository binding to root commit and/or remote origin.

The plan currently implies that this is sufficient to prevent repository spoofing.

That statement should be softened.

## Important distinction

A root commit or remote-origin value is an **identity/binding signal**, not a universal cryptographic proof of repository ownership.

For example:

- a root commit can be copied into another repository,
- remote URLs are configuration data and are not themselves cryptographic proof.

## Recommendation

Define the local trust process as:

```text
User explicitly establishes trust
        ↓
TrustedProjectEntry
        ↓
Stable project/repository binding
        ↓
Trusted Authority Key
```

The architecture should explicitly state:

> The trust store represents the user's out-of-band trust decision. Repository binding reduces accidental or malicious substitution but does not claim to provide a universal global identity for a Git repository.

This is more technically defensible and still works with the local-first design.

---

# 5. P0 — Distinguish Approval Signing From Git Commit Signing

The current architecture correctly introduces:

```text
IdentityPort
SignaturePort
```

and cryptographic ChangeSet approvals.

Keep this.

But make the distinction explicit:

```text
Git Commit Signature
    ≠
ChangeSet Approval Signature
```

They may use the same underlying SSH/GPG key, but they are different artifacts with different semantic purposes.

Recommended:

```text
ApprovalSignature
├── actor
├── ChangeSet digest
├── policy version
├── project identity
├── timestamp
└── signature
```

Git commit signing proves/attests to a commit.

ChangeSet approval authorizes a specific platform operation.

Do not treat them as interchangeable merely because the same key may be used.

---

# 6. P0 — Revalidate the Policy Chain at Apply Time

The plan now correctly revalidates:

- ChangeSet digest,
- base revision,
- working-tree fingerprint,
- policy version,
- approval signature,
- staged output,
- capabilities.

Keep all of these.

One additional clarification:

> The policy version should not be the only policy check.

The Policy Engine should re-evaluate the actual current policy against the operation.

Recommended:

```text
Stored approval context
+
Current policy
+
Current actor capabilities
+
Current operation
+
ChangeSet
        ↓
Final Policy Decision
```

This ensures that policy semantics, not merely a matching digest, remain authoritative.

The active policy version/digest remains useful as audit evidence.

---

# 7. P0 — Clarify Approval Requirements for Staging vs Target Mutation

There is a subtle tension in the current plan.

The Policy Engine currently describes approval requirements before:

> "any staging mutation, target application, or privileged command execution."

Yet the architecture also intends to support:

> automated self-repair inside isolated staging.

These can coexist, but the approval boundary should be clearer.

## Recommended distinction

```text
Analysis
    → usually no approval

Plan generation
    → usually no approval

Isolated staging mutation
    → policy-controlled
    → may be autonomous for low-risk changes

Validation in staging
    → policy-controlled

Target working-tree mutation
    → human approval required unless explicitly delegated by policy

Security/policy changes
    → elevated authority approval

Privileged execution
    → policy-defined approval
```

The key invariant should remain:

> **No unapproved agent-generated mutation reaches the authoritative target repository.**

Do not accidentally make every temporary staging write require manual approval unless that is deliberately chosen for a specific workflow.

This matters for the "self-improving / bounded repair" behavior.

---

# 8. P0 — Event Logging Must Be Treated as a Data-Handling Boundary

The architecture correctly defines SQLite as the canonical operational event store and JSONL as an audit mirror.

However, command output, diagnostics, tool results, and agent context may contain:

- secrets,
- source code,
- tokens,
- internal URLs,
- customer data,
- sensitive environment values.

The current invariant says secrets are sanitized, but relying on generic secret detection is not sufficient.

## Recommendation

Define an event-data classification policy:

```text
Event Metadata
    → always persist

Structured diagnostic
    → persist after sanitization

Raw command stdout/stderr
    → bounded and sanitized

Raw environment
    → never persist

Raw credentials/secrets
    → never persist

Full model/context payloads
    → do not persist by default
```

Prefer references/digests over storing huge or sensitive raw payloads.

For example:

```text
ValidationResult
├── exit_code
├── status
├── duration
├── diagnostics_summary
├── output_digest
└── sanitized_excerpt
```

This reduces the risk that the audit subsystem itself becomes a sensitive-data leak.

---

# 9. P1 — "100% Local" Must Be Distinguished From "Data Never Leaves the Machine"

The plan uses BYOK/model APIs and describes the platform as:

> "100% local, Git-native fidelity."

This is ambiguous.

The platform runtime may be local while the LLM provider is remote.

For example:

```text
Local Platform
    ↓
OpenAI / other Model API
    ↓
Data potentially leaves workstation
```

## Recommendation

Distinguish:

### Execution locality

```text
Core process
GUI
Git
Run store
Policy Engine
```

are local.

### Model/data locality

May be:

```text
Local model
or
Remote model API
```

depending on the configured AgentRuntime adapter.

This should lead to an explicit policy:

```text
Model Provider Policy
├── local-only
├── approved remote provider(s)
├── data classes allowed for remote transmission
└── redaction requirements
```

This is important for the platform's eventual enterprise/security story.

It does not require a central server.

---

# 10. P1 — Secret Handling Needs "Ephemeral Scoped Injection"

The current plan says environment variables containing secrets should be stripped.

That is safe but may prevent legitimate workflows.

Some validation commands genuinely require:

```text
API credentials
test database credentials
package registry credentials
cloud credentials
```

The correct model is not:

> never allow secrets during execution.

It is:

> **Never persist secrets; only inject explicitly approved secrets into explicitly authorized execution contexts.**

Recommended:

```text
Secret Store
    ↓
Policy Decision
    ↓
Ephemeral scoped injection
    ↓
Process
    ↓
Environment destroyed
```

Rules:

- secret names/values are not written to logs,
- secret values are not written to ChangeSet digests,
- secrets are not committed to Git,
- only approved workflows can request them,
- each secret has a defined scope and lifetime.

This is more practical than universally stripping every secret from every command environment.

---

# 11. P1 — Define the Default Network Policy

The execution model now includes network restrictions.

The architecture should define a default posture.

Recommended:

```text
Untrusted Repository
    → Network Denied

Trusted Repository
    → Network Policy Required

Specific Workflow
    → Explicit egress allowlist where needed
```

This is particularly important because package managers and tests may implicitly access the network.

The policy should distinguish:

```text
No network
Limited network
Explicitly allowed destinations
Unrestricted network
```

Do not assume that an allowlisted command is safe merely because its executable name is approved.

---

# 12. P1 — Add a Policy for Tool/Workflow Installation

The plan protects workflow definitions through capability declarations.

That is good.

A future workflow can still be executable code.

The architecture should define a lifecycle:

```text
Discover workflow
    ↓
Verify publisher/trust where applicable
    ↓
Inspect capabilities
    ↓
Policy evaluation
    ↓
Install/enable
    ↓
Record version and trust state
```

For the initial local-only MVP, project-owned workflows may be explicitly trusted.

Do not build a marketplace.

The goal is simply to prevent an installed workflow from silently acquiring capabilities beyond its declared/policy-approved scope.

---

# 13. P1 — Clarify the Difference Between Project Policy and Local User Policy

The plan now has:

```text
Project policy
```

and:

```text
Local trust/configuration
```

Make the precedence explicit.

Recommended conceptual layers:

```text
Platform Defaults
       ↓
Project Policy
       ↓
Local User Policy / Overrides
       ↓
Operation
```

But local overrides must not be able to weaken protected security invariants without the correct authority.

For example:

```text
Developer local config
    cannot disable:
        approval for protected apply
        signature validation
        protected path rules
```

unless the operation is explicitly governed by a trusted authority.

This avoids configuration precedence becoming a hidden security bypass.

---

# 14. P1 — Clarify Policy Version vs Policy Digest

The plan currently uses "policy version" and content digests.

Prefer both:

```text
policy_id
policy_schema_version
policy_revision
policy_content_digest
```

A human-readable revision might be:

```text
policy_revision: 17
```

while the immutable identity of the exact policy is:

```text
policy_content_digest: sha256:...
```

Approval and audit records should bind to the content digest, not merely the numeric revision.

---

# 15. P1 — Make ChangeSet Digest Composition Explicit

The current ChangeSet model includes:

```text
base_revision
worktree_fingerprint
changed_paths
file_operations
content_digests
change_set_digest
```

Good.

Add an explicit statement that the root ChangeSet digest covers the complete canonical representation, including at minimum:

```text
project identity
workspace scope
base revision
base worktree fingerprint
normalized paths
operations
file content digests
file modes
policy context where appropriate
schema version
```

The exact inclusion list should be finalized before implementation.

The invariant should be:

> Any semantically relevant modification to a ChangeSet must alter its digest.

---

# 16. P1 — Be Precise About "Working-Tree Fingerprint"

The current plan uses:

```text
worktree_fingerprint
```

and says untracked/modified files cause `BaseChanged`.

Define what the fingerprint covers.

At minimum consider:

```text
tracked file contents
file modes
symlink targets/types
relevant repository metadata
```

Separately record:

```text
untracked files
ignored files
submodule state
```

where applicable.

Do not assume "Git commit SHA" alone represents the working tree.

The exact fingerprint algorithm can be implementation-defined, but the scope needs to be stated.

---

# 17. P1 — Recovery State Should Preserve Operator Next Steps

The plan already has:

```text
RecoveryRequired
```

Make it operationally useful.

A `RecoveryRequired` state should expose:

```text
What happened
What state was detected
What files may have been affected
What rollback was attempted
What succeeded
What failed
What the user should do next
Whether automatic retry is forbidden
```

This directly supports the GUI's requested:

- details,
- help,
- next steps.

---

# 18. P1 — Add Idempotency to Control API Commands

The Control API is now the GUI/core boundary.

Consider commands such as:

```text
ApprovePlan
ApplyChangeSet
StartRun
CancelRun
RetryRun
```

If the browser retries a request, the command should not accidentally execute twice.

## Recommendation

For mutating Control API operations, support an operation/request ID:

```text
request_id
```

and make the core handle duplicate requests idempotently where possible.

This is especially important around:

```text
ApplyChangeSet
ApproveChangeSet
```

---

# 19. P1 — GUI Session Token Should Not Be Treated as Authorization

The current plan correctly makes the GUI token a per-launch session credential.

Keep it.

But explicitly define:

```text
Session token
=
"this request belongs to the currently authenticated local session"

Authorization
=
Policy Engine decision for the Actor
```

The token must never itself grant a role.

The core should resolve:

```text
token → Actor → authorization
```

and re-check permissions for sensitive operations.

---

# 20. P1 — Consider a Stronger Apply Strategy Before Coding It

The current architecture applies validated ChangeSets into the target working tree.

This can work.

However, a safer long-term mechanism may be:

```text
Target repository
       ↓
Temporary Git worktree / branch
       ↓
Apply ChangeSet
       ↓
Validate
       ↓
Create commit
       ↓
Human integrates/accepts result
```

This provides stronger isolation between:

```text
agent execution
```

and:

```text
developer's current working tree
```

It is not mandatory to adopt this if the implementation has a strong reason to use direct application.

The important point is:

> Resolve the apply strategy explicitly before implementation, because it affects recovery, conflict handling, and user experience.

---

# 21. P1 — Clarify Commit Attribution vs Commit Authorization

The plan distinguishes:

```text
requested_by
proposed_by
approved_by
committed_by
```

This is excellent.

Maintain the distinction between:

```text
commit attribution
```

and:

```text
commit authorization
```

An agent-specific Git identity can identify that a platform component created a commit.

It does not, by itself, prove that the commit was authorized.

Authorization evidence should remain linked to:

```text
ChangeSet
Approval
Policy decision
```

---

# 22. P2 — Distribution & IP Protection Should Remain a Release-Hardening Concern

The platform should remain local-first.

The separate publishing/distribution strategy can later cover:

- production packaging,
- signed binaries,
- signed releases,
- workflow package trust,
- update verification,
- proprietary-core protection,
- optional protected services for true crown-jewel logic.

Do not introduce distribution complexity into the current core architecture before the core contracts stabilize.

Also preserve the important limitation:

> Client-side code that executes on the user's machine cannot be made absolutely secret from a determined user.

---

# 23. P2 — Platform Command Naming Should Be Finalized Before Release

The plan still references both:

```text
agent
```

and:

```text
migration-agent
```

as command names.

That is understandable during transition.

Before implementation reaches packaging/release, choose a canonical public command:

```text
agent
```

is the natural project-neutral name.

If backward compatibility is required:

```text
migration-agent
    → compatibility alias
```

Do not let naming transition leak into APIs, documentation, and packaging indefinitely.

---

# 24. What I Would NOT Change

Do not change these successful architectural decisions:

### Keep

- local-first architecture,
- no mandatory centralized auth server,
- no mandatory authorization server,
- Git-native project governance,
- out-of-band trust store,
- Policy Engine,
- capability-based authorization,
- IdentityPort + SignaturePort,
- isolated staging,
- digest-bound approval,
- base-state binding,
- Run/Event model,
- challenge/solution/learning provenance,
- epistemic status,
- decoupled GUI,
- versioned Control API,
- workflow modules,
- project-neutral core,
- optional hardened sandbox,
- deferred global learning.

### Do not add

- mandatory cloud backend,
- enterprise RBAC implementation in MVP,
- mandatory vector database,
- mandatory containers,
- full Web IDE,
- Jira/Confluence-style project management,
- central database for project state.

---

# 25. Final Implementation Gate

After Antigravity incorporates or explicitly rejects the remarks above, I recommend treating the architecture as **stable**.

At that point the remaining work should move into:

```text
Implementation
    ↓
Unit Tests
    ↓
Integration Tests
    ↓
Adversarial Security Tests
    ↓
Failure/Recovery Tests
    ↓
Performance Tests
    ↓
User/UX Validation
    ↓
Release Hardening
```

Do not keep reopening architecture indefinitely unless implementation evidence reveals a genuine architectural defect.

---

# 26. Instructions to Antigravity / Codex

Use this document as the final targeted reconciliation pass.

## Required

1. Review each P0/P1/P2 item.
2. Accept, refine, or explicitly reject each item.
3. Correct the RFC 8785/file-content hashing issue.
4. Correct any "atomic apply" language that overstates guarantees.
5. Clarify Authority Key trust binding without claiming impossible global repository identity.
6. Distinguish identity verification, signing, approval, and commit attribution.
7. Clarify staging-approval semantics so bounded self-repair remains practical.
8. Treat event persistence as a sensitive data-handling boundary.
9. Distinguish local execution from model/data locality.
10. Define scoped/ephemeral secret injection where required.
11. Clarify policy precedence and digest semantics.
12. Clarify ChangeSet and worktree fingerprint composition.
13. Add idempotency expectations to mutating Control API operations.
14. Preserve `RecoveryRequired` as a real operational safety state.
15. Resolve the final target-apply strategy before implementation.

## Do not

- redesign the platform,
- expand the scope,
- introduce mandatory centralized infrastructure,
- convert deferred capabilities into MVP requirements,
- or claim stronger guarantees than can be demonstrated through testing.

## After reconciliation

Report:

- accepted recommendations,
- refined recommendations,
- rejected recommendations and reasons,
- changed ADRs,
- changed invariants,
- changed contracts,
- remaining deferred items,
- final implementation readiness,
- tests required to prove the remaining security/correctness claims.

---

# 27. Final Position

The platform is now at the point where:

> **Architecture should become stable and implementation should become the primary source of evidence.**

The remaining issues are mostly precision and hardening concerns, not evidence that the architectural direction is wrong.

Once the final points above are reconciled, proceed to implementation and let automated/adversarial testing validate the guarantees rather than continuing to expand the architecture document indefinitely.
