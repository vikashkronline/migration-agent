# Agent Platform — Final Plan Reconciliation Instructions

## Purpose

This document is the final, focused reconciliation note for the current Agent Platform architecture plan.

The latest architecture reconciliation is strong and should now be treated as the baseline rather than reopening the broader product-scope discussion.

The purpose of this document is to ask Antigravity / Codex to perform one **small final architecture pass** over the reconciled plan, focused only on the remaining trust, correctness, and terminology issues identified in the final review.

Do not redesign the platform.

Do not broaden the scope.

Do not introduce a centralized authentication server, authorization server, mandatory cloud backend, mandatory container runtime, or embedded GUI.

The objective is to make the current plan precise enough that implementation can begin without creating avoidable architectural ambiguity.

---

# 1. Final Position

The architecture is considered:

> **Feasible and ready to begin implementation, with no known fundamental architectural blocker.**

However, this should **not** be expressed as:

> "zero architectural or technical blocker"  
> "fully validated"  
> "production-ready"

because implementation-level security and correctness still need to be demonstrated through code, automated tests, integration tests, and adversarial failure-case testing.

Recommended wording for the master plan:

> **No known fundamental architectural blocker remains. Implementation may proceed, but all security and correctness invariants must be demonstrated by automated tests and adversarial failure-case validation before the platform is considered production-ready.**

---

# 2. Do Not Reopen the Product-Scope Decision

The current architecture successfully preserved the intended direction:

- project-neutral core,
- headless engine,
- local-first execution,
- Git-native governance,
- decoupled GUI,
- centralized Policy Engine,
- controlled agent execution,
- human approval,
- provenance-backed learning,
- additive workflow modules,
- no mandatory centralized backend.

Do not expand the system back into:

- Jira replacement,
- Confluence replacement,
- Backstage replacement,
- full Web IDE,
- enterprise IAM platform,
- centralized project database,
- mandatory cloud coordinator,
- autonomous self-rewriting platform.

Concrete project-specific migration workflows must remain extensions/examples, not definitions of the reusable core.

---

# 3. Final Remaining Issue #1 — Trust Bootstrap Binding

The current design correctly introduced:

```text
~/.agent-platform/trust/<project-id>.json
```

as an out-of-band trust store for Authority Keys.

This resolves the original circular-trust problem.

## Remaining question

The master plan must define:

> **How does the local trust record establish that the repository being opened is the same project for which the Authority Key was trusted?**

Do not rely solely on:

```text
.agent/manifest.json
```

for this binding because repository-controlled metadata may itself be modified.

## Recommended conceptual binding

A trust entry should contain a stable project/repository binding in addition to the trusted Authority Key.

Conceptually:

```text
TrustedProjectEntry
├── project_id
├── repository_binding
├── authority_keys
├── trust_state
├── created_at
└── last_updated_at
```

`repository_binding` may incorporate an appropriate stable repository identity or equivalent mechanism.

The exact mechanism can be chosen during implementation.

The architecture must also account for:

- authority key rotation,
- authority key revocation,
- multiple trusted authority keys,
- trust reset/rebootstrap,
- lost authority keys.

Do not introduce a central service merely to solve this.

---

# 4. Final Remaining Issue #2 — Identity vs Signing Must Be Explicitly Separated

The current domain already contains:

```text
Actor
cryptographic_identity
AuthorizationDecision
Approval
```

This is correct.

However, distinguish these concepts explicitly:

```text
Identity Verification
=
Who is this actor?

Signing
=
Can this actor cryptographically authorize this artifact/action?
```

The architecture should provide a suitable boundary such as:

```text
IdentityPort
Signature/SigningPort
```

or an equivalent combined abstraction if the resulting responsibilities remain explicit.

The system should support:

```text
Resolve actor identity
Verify signature
Produce approval signature
Verify approval signature
```

Do not assume that merely knowing an SSH/GPG fingerprint means the application can produce a signature.

This is especially important for digest-bound ChangeSet approval.

---

# 5. Final Remaining Issue #3 — Local GUI Session Must Be Explicitly Mapped to Actor Identity

The current GUI model uses:

```text
localhost
+
per-launch token
+
OS user
+
local Git identity
```

This is a good model, but define the relationship precisely.

Recommended conceptual flow:

```text
GUI Launch
    ↓
Local Session Created
    ↓
Actor Resolution
    ↓
Identity / Trust Verification
    ↓
Session Bound to Actor
    ↓
Privileged Request
    ↓
Core Re-checks Authorization
```

Do not trust:

```text
git config user.name
git config user.email
```

as authentication proof.

They may remain display metadata.

The previously defined assurance modes should remain:

```text
Mode A — Cryptographically Verified
Mode B — Trusted Local Session
Mode C — Read-Only Inspection
```

The plan should define which operations require which level.

---

# 6. Final Remaining Issue #4 — ChangeSet Apply Must Revalidate the Complete Security Chain

The current ChangeSet design already includes:

```text
base_revision
base_tree_fingerprint
ChangeSet digest
approval
policy version
```

Before final APPLY, explicitly revalidate all relevant bindings.

Recommended:

```text
Approved ChangeSet
        +
Current Target Base
        +
Current Policy Version
        +
Approval Signature
        +
Staged ChangeSet
        ↓
Final Apply Authorization
```

Before mutation, verify at minimum:

1. ChangeSet digest is unchanged.
2. Base repository revision is unchanged.
3. Working-tree fingerprint is unchanged.
4. Active policy version is unchanged or still valid.
5. Approval remains valid.
6. Staged output corresponds to the approved ChangeSet.
7. No conflicting human modifications exist.
8. Required capabilities are still present.

If any of these fail:

```text
Apply
 ↓
Blocked
 ↓
Approval invalidated where appropriate
 ↓
Re-inspection / re-planning
```

Do not silently reuse stale approval.

---

# 7. Final Remaining Issue #5 — Repository Drift Invalidates More Than Approval

The current plan correctly introduces:

```text
BaseChanged
```

and stale approvals.

Make the consequence explicit.

If the target repository diverges after approval, invalidate:

```text
Approval
+
Validated Staging Result
+
Validation Result
```

as applicable.

Recommended:

```text
BaseChanged
    ↓
Existing approval = invalid
Existing stage = invalid
Existing validation = invalid
    ↓
Re-inspect
    ↓
Re-plan
    ↓
New ChangeSet
    ↓
New approval
```

Do not apply an old validated stage to a new base.

---

# 8. Final Remaining Issue #6 — Repair Loop Must Always Create a New Security Context

The current plan correctly says repairs create new ChangeSets.

Make the security semantics completely explicit:

```text
ValidationFailed
      ↓
RepairProposal
      ↓
New ChangeSet
      ↓
New ChangeSet Digest
      ↓
Fresh Policy Evaluation
      ↓
Fresh Approval
      ↓
New Staging
      ↓
Validation
```

Never allow:

```text
approved ChangeSet
    ↓
silent mutation
    ↓
"same approval still applies"
```

Any mutation of the actual proposed change invalidates the old approval.

---

# 9. Final Remaining Issue #7 — Rollback Must Not Be Promised as Universal

The current plan uses language such as:

> "automatic rollback"

and:

> "changes are cleanly reverted."

The implementation should aim for robust rollback/recovery, but the architecture should not promise universal automatic recovery.

There are failure conditions such as:

- disk failure,
- permission failure,
- file locking,
- abrupt process termination,
- external modification,
- filesystem anomalies.

Recommended state model:

```text
Apply Failure
    ↓
Attempt rollback
    ↓
Verify resulting state
    ↓
┌───────────────────────────────┐
│ Complete rollback             │
│ or                            │
│ RecoveryRequired              │
└───────────────────────────────┘
```

`RecoveryRequired` should be a real safety state.

The core invariant should be:

> **The platform must never silently assume that rollback succeeded.**

---

# 10. Final Remaining Issue #8 — Canonical Event Store vs Tamper Evidence

The current plan correctly defines:

```text
SQLite = canonical operational store
JSONL = audit/export mirror
```

Keep that decision.

However:

> **Canonical does not mean tamper-proof.**

A local SQLite database is controlled by the local user/process.

Therefore separate:

```text
Operational Run History
```

from:

```text
Tamper-Evident Security Evidence
```

Recommended conceptual model:

```text
SQLite
=
canonical operational execution state

Cryptographic digests/signatures
=
tamper evidence

Git
=
durable project governance state
```

Security-sensitive events should be linked where practical through:

- ChangeSet digests,
- approval signatures,
- policy-version digests,
- commit hashes,
- event-hash chains or equivalent tamper-evidence mechanisms.

Do not claim that local SQLite is immutable.

---

# 11. Final Remaining Issue #9 — Correct the "Git as Audit" Wording

The reconciled report says:

> "Git serves as the durable audit and governance layer."

This is broader than the storage architecture actually specifies.

The more precise model is:

```text
Git
=
durable project governance and version history

SQLite
=
canonical local execution/run state

JSONL
=
audit/export representation

Cryptographic signatures/digests
=
tamper evidence for security-sensitive records
```

Update executive-level wording accordingly.

---

# 12. Final Remaining Issue #10 — Do Not Call Native Process Execution a Strong Sandbox

The architecture correctly introduced `ExecutionSandboxPort`.

Keep that abstraction.

However, distinguish:

```text
Native Controlled Execution
```

from:

```text
Hardened Sandbox Execution
```

Native execution can provide:

- working-directory confinement,
- environment sanitization,
- command policy,
- process tracking,
- timeout,
- policy checks.

But without stronger OS/container/VM isolation, it cannot guarantee the same isolation properties as a real sandbox.

Recommended model:

```text
ExecutionSandboxPort
├── NativeExecutionAdapter
└── HardenedSandboxAdapter (future/optional)
```

For untrusted repositories, default to restricted/static analysis until execution is explicitly enabled.

---

# 13. Final Remaining Issue #11 — Event Sourcing Terminology

The current plan describes the Run lifecycle as event-sourced.

That terminology should match the implementation.

Choose one:

## Full event sourcing

```text
Events
  ↓
Projection
  ↓
Current State
```

Events are the authoritative state representation.

## State + Audit Events

```text
Current Run State
+
Append-only audit events
```

The architecture should not claim full event sourcing unless the events are actually authoritative.

Either model is valid.

The important requirement is consistency.

---

# 14. Final Remaining Issue #12 — Project-Specific Migration Must Not Leak Into Platform Definition

The current plan has already improved this significantly.

Ensure that:

```text
Migration & Refactoring Workflow
```

is a reusable capability.

A specific migration such as:

```text
Ember Classic → Angular Standalone
```

must remain:

```text
project-specific workflow
or
reference/example workflow
```

rather than a core platform responsibility.

This preserves project neutrality.

---

# 15. Final Remaining Issue #13 — Generated Artifact Regeneration Contract

The plan now distinguishes:

```text
Generated
Human-Authored
Human-Modified Generated
```

Preserve this.

Also make behavior explicit:

```text
Generated
    → may regenerate

Human-Modified Generated
    → show diff / reconcile

Human-Authored
    → never silently overwrite
```

The same principle should apply to:

- Mermaid diagrams,
- architecture documents,
- generated specifications,
- reports,
- extracted project models.

---

# 16. Final Remaining Issue #14 — Challenge/Solution/Learning Evidence

The current typed lifecycle is good.

The intended lifecycle should remain:

```text
Challenge
    ↓
Analysis
    ↓
Candidate Solution
    ↓
Experiment / Implementation
    ↓
Evidence
    ↓
Verification
    ↓
Human Review
    ↓
Approved Learning
```

A successful LLM response alone must never be treated as sufficient evidence for a durable learning.

Evidence should preferably reference:

- test results,
- validated behavior,
- source changes,
- execution runs,
- diagnostics,
- architectural decisions.

---

# 17. Final Remaining Issue #15 — ContextEnvelope

The current plan includes contextual Q&A and a `ContextEnvelope`.

Ensure the model is explicit enough to prevent the agent from receiving indiscriminately large project context.

Conceptually:

```text
ContextEnvelope
├── project_ref
├── selected_entity
├── selected_artifact
├── selected_work_item
├── current_run
├── active_policy_version
├── relevant decisions
├── relevant learnings
├── evidence references
└── user request
```

The flow should be:

```text
User selects context
        ↓
Context Resolver
        ↓
Relevant evidence
        ↓
ContextEnvelope
        ↓
Agent Runtime
```

This keeps contextual interaction scoped, traceable, and efficient.

---

# 18. Final Remaining Issue #16 — Control API Contract

The current plan has:

```text
control_api_version: "1.0"
```

and a typed handshake.

Keep this.

The final plan should explicitly state that these are versioned contracts:

- commands,
- queries,
- event schemas,
- errors,
- capability responses.

The GUI should declare its supported Control API version.

This allows:

```text
Core upgrade
+
GUI upgrade
```

to be decoupled.

---

# 19. Final Remaining Issue #17 — GUI Must Preserve Full Product Vision

The architectural simplification must not accidentally reduce the GUI to only a diff viewer.

The final product vision should retain appropriate support for:

```text
Project
├── Objectives
├── Requirements
├── Workstreams
├── High-Level Steps
├── Low-Level Tasks
├── Progress
├── Current State
├── Agent Activity
├── Challenges
├── Solutions
├── Decisions
├── Architecture
├── Documentation
├── Artifacts
├── References
├── Help
├── Next Steps
└── History / Audit
```

The GUI should remain a control center rather than becoming a replacement for Jira/Confluence/IDE.

---

# 20. Final Recommended Architecture Statement

The master plan should converge on a statement similar to:

> **The Agent Platform is a local-first, Git-native, project-neutral agent execution and engineering-control platform. Its headless core exposes stable domain contracts and a typed Control API, while a decoupled local GUI provides the interactive presentation surface. Agent proposals are untrusted; policy, authorization, approval, staging, validation, and controlled application are enforced by deterministic platform components. Project state and governance are versioned in Git, while local run/runtime state remains outside the repository. The architecture supports additive workflows and adapters without requiring normal project-specific capabilities to modify the core.**

---

# 21. Final Readiness Statement

Replace overly strong claims such as:

> "Zero architectural or technical blocker remains."

with:

> **No known fundamental architectural blocker remains. The architecture is ready to begin implementation, subject to validating its security, correctness, recovery, and isolation invariants through automated, integration, and adversarial tests.**

This is the correct point at which to start implementation.

The distinction is important:

```text
Architecture
     ↓
Feasible and implementation-ready

Implementation
     ↓
Must still prove:
- security
- correctness
- recovery
- isolation
- determinism
```

---

# 22. Recommended Pre-Implementation Validation Tests

Before declaring the corresponding core capabilities production-ready, the implementation should eventually test at least these scenarios.

## Identity / Authorization

- modified role policy is rejected without valid authority.
- unknown Authority Key is rejected.
- trust binding mismatch is rejected.
- invalid signature is rejected.
- revoked key is rejected.
- lower-assurance identity cannot perform high-assurance operations.

## ChangeSet

- modified ChangeSet digest invalidates approval.
- modified base revision invalidates approval.
- modified working tree invalidates approval.
- modified policy invalidates approval where required.
- modified staged output is rejected.
- repair creates a new approval chain.

## Apply / Recovery

- conflicting user change is not overwritten.
- dry-run failure prevents apply.
- partial apply enters a recoverable state.
- rollback failure leads to `RecoveryRequired`.
- restart after process crash reconciles actual repository state before continuing.

## Event Store

- events remain ordered.
- duplicate events are detectable/handled.
- restart does not duplicate irreversible effects.
- JSONL export cannot silently become a competing source of truth.
- tamper-evidence checks detect modified security-sensitive records.

## Execution

- untrusted repository defaults to restricted mode.
- disallowed command is blocked.
- disallowed arguments are blocked.
- working-directory escape is blocked.
- environment secrets do not enter persisted logs.
- timeout terminates execution.
- child-process behavior is tracked.
- native execution limitations are clearly reported.

## GUI

- GUI cannot bypass backend policy.
- invalid/expired local token is rejected.
- malformed origin is rejected.
- CSRF attempt is rejected.
- GUI shows `PolicyBlocked`, `BaseChanged`, `Conflict`, `RecoveryRequired`, and related states correctly.
- GUI consumes the Control API rather than local storage internals.

---

# 23. Instructions to Antigravity / Codex

Perform **one final reconciliation pass** over the master architecture plan using this document.

### Do

1. Compare every recommendation with the current plan.
2. Resolve only the remaining ambiguities and overstatements.
3. Update the relevant ADRs and invariants.
4. Ensure trust bootstrapping is explicitly bound to the intended project/repository.
5. Clarify identity vs signing.
6. Clarify final ChangeSet/apply revalidation.
7. Clarify rollback/recovery guarantees.
8. Clarify canonical event storage versus tamper evidence.
9. Clarify native execution versus hardened sandboxing.
10. Clarify event-sourcing terminology.
11. Preserve project neutrality.
12. Preserve the full intended GUI/control-center scope.
13. Keep deferred features deferred.

### Do not

- redesign the overall architecture,
- add a mandatory authentication server,
- add a mandatory authorization server,
- add a mandatory cloud backend,
- add a mandatory container runtime,
- turn the project into an enterprise ALM platform,
- move project-specific migration logic into the core,
- claim stronger security guarantees than the implementation can actually enforce.

---

# 24. Final Expected Response From Antigravity / Codex

After reconciliation, report:

1. Which points were already covered.
2. Which points were changed.
3. Which points were intentionally rejected.
4. Which ADRs/invariants changed.
5. Which trust boundaries are now explicit.
6. What remains intentionally deferred.
7. Whether any fundamental blocker remains.
8. Which tests must prove the architecture before calling the implementation production-ready.

Do not begin unrelated implementation in this reconciliation step.

---

# 25. Final Principle

The architecture is now at the correct point to move from:

```text
Architecture Discovery
        ↓
Architecture Reconciliation
        ↓
Implementation
```

The goal is no longer to make the architecture "perfect."

The goal is to make the remaining assumptions:

- explicit,
- testable,
- enforceable,
- traceable,
- versioned,

while preserving the project's core direction.

> **Proceed to implementation once these final semantic clarifications are incorporated. Treat security and correctness claims as hypotheses until implementation and adversarial testing demonstrate them.**
