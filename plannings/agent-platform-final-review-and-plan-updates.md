# Agent Platform — Final Architecture Review Remarks & Recommended Plan Updates

## Purpose

This document is the final review of the current Agent Platform architecture plan.

The current plan is now substantially mature and internally coherent. The recommendations below are intended to close the remaining architectural gaps, remove a few internal ambiguities, and prevent implementation decisions from creating avoidable refactoring later.

Use this document together with the current architecture plan.

**Do not blindly apply every recommendation.** Antigravity/Codex should compare each item against the current design, preserve already-correct decisions, and update the main plan only where the recommendation improves consistency, safety, feasibility, or alignment with the original product intent.

The objective remains:

> Build a reusable, project-neutral, local-first agent platform whose core supports future workflows and project-specific extensions without fundamental architectural refactoring; whose agent actions are controlled, auditable, and verifiable; and whose GUI is a decoupled control surface over the same platform state.

---

# 1. Overall Final Assessment

## Verdict

The architecture is **feasible and worth proceeding with**.

There is no fundamental technology or architectural blocker that requires changing the overall direction.

The strongest aspects of the current plan are:

- headless core,
- decoupled local GUI,
- Git-native project governance,
- capability-based authorization,
- explicit identity boundary,
- centralized Policy Engine,
- controlled mutation lifecycle,
- digest-bound ChangeSets and approvals,
- project-level provenance-backed learning,
- observed/inferred/human-confirmed knowledge states,
- explicit Run/Event model,
- repository/local-runtime state separation,
- additive workflow/module architecture,
- explicit security limitations around local hooks.

The remaining issues are primarily **trust bootstrapping, lifecycle semantics, operational safety, state contracts, and preservation of the original product scope**.

---

# 2. Priority Classification

The recommendations in this document are classified as:

### P0 — Resolve before implementation of the affected core

These can create security or correctness problems if left ambiguous.

1. Trust bootstrap for Authority Keys.
2. Clear authentication assurance levels.
3. Exact ChangeSet/base revision semantics.
4. Repair-loop re-approval semantics.
5. Canonical event-store definition.
6. Safe apply/reconciliation semantics.
7. Security limits of process/network isolation.

### P1 — Resolve before Phase 2/3 implementation

These should be defined before the corresponding features become substantial.

8. Artifact ownership/generated-vs-human-edited model.
9. Project/workspace/monorepo model.
10. Challenge → Solution → Learning lifecycle.
11. Global/platform knowledge vs project knowledge.
12. Control API contract and versioning.
13. GUI security model.
14. Run terminal/error/conflict states.

### P2 — Can remain deferred

15. Enterprise identity providers.
16. Shared/remote run history.
17. Global learning exchange.
18. Advanced sandbox backends.
19. Remote execution.

---

# 3. P0 — Authority Key Trust Bootstrapping Is Still Underspecified

## Current design

The plan correctly introduces:

- Git-native identities,
- Authority Keys,
- signed/verified policy,
- protection against self-authorization.

This is one of the strongest security improvements in the revised plan.

However, one trust problem remains:

```text
principals.json
    ↓
contains Authority Key
```

If an attacker can modify both:

```text
principals.json
```

and:

```text
roles/policy
```

then simply storing the Authority Key inside repository-controlled files does not establish that the Authority Key itself is trusted.

## Recommendation

Define a **trust bootstrap/root-of-trust mechanism**.

Conceptually:

```text
Trusted Root
    ↓
Authority Key(s)
    ↓
Signed Access Policy
    ↓
Roles
    ↓
Capabilities
```

The trusted root should not be completely mutable by the same policy it is intended to authorize.

Possible initial implementation approaches include:

```text
~/.agent-platform/trust/<project>.json
```

or an explicit command such as:

```text
agent trust add-key <fingerprint>
```

or another local trust store.

The exact implementation can be decided later, but the architecture must answer:

> How does the platform know that this Authority Key is trusted before it reads the repository's authorization policy?

Also define:

- authority-key rotation,
- authority-key revocation,
- multiple authority keys,
- trust reset/rebootstrap,
- what happens when the trusted key is lost.

Do not introduce a central server merely to solve this.

---

# 4. P0 — Authentication Assurance Levels Need to Be Explicit

The current ADR allows:

```text
cryptographic Git identity
```

with:

```text
LocalTrustedUser
```

as a fallback for initial offline prototyping.

This is reasonable, but these are not equivalent authentication strengths.

## Recommendation

Define explicit assurance modes.

For example:

```text
Mode A — Cryptographically Verified
    Git/SSH/GPG identity verified.

Mode B — Local Trusted Session
    OS user + locally launched trusted process.

Mode C — Unauthenticated/Inspection Only
    Read-only analysis with no security-sensitive actions.
```

Then explicitly define which operations require which assurance level.

For example:

```text
Read project
    → Mode C or above

Generate analysis
    → Mode C or above

Approve ChangeSet
    → Mode A or trusted local owner policy

Change security policy
    → Mode A / Authority Key

Apply ChangeSet
    → Policy-defined assurance
```

Do not describe `LocalTrustedUser` as equivalent to cryptographic authentication.

This keeps the local-first architecture intact while making the trust model honest.

---

# 5. P0 — ChangeSet Must Be Bound to a Base Repository State

The current plan correctly binds approval to a ChangeSet digest.

However, the plan should also define the **base state against which the ChangeSet was generated**.

Suppose:

```text
Run starts at commit A
        ↓
ChangeSet generated
        ↓
Human approval
        ↓
Developer modifies repository
        ↓
Agent applies ChangeSet
```

The ChangeSet may no longer be safe to apply.

## Recommendation

Every ChangeSet should contain at least:

```text
ChangeSet
├── change_set_id
├── project_id
├── base_revision
├── source/worktree state fingerprint
├── changed paths
├── file content digests
├── file mode metadata
├── operation type
└── ChangeSet digest
```

Before `APPLY`, the platform must verify that the target state still matches the expected base.

If not:

```text
APPLY
  ↓
Base mismatch
  ↓
Invalidate approval
  ↓
Re-inspect / re-plan / re-approve
```

Do not silently perform a three-way merge unless the policy explicitly allows it and the resulting ChangeSet is represented and approved as a new artifact.

---

# 6. P0 — ChangeSet Canonicalization Must Be Defined

The architecture relies heavily on content digests.

Therefore the plan needs a conceptual canonicalization contract.

Specify how digests handle:

- text encoding,
- line endings,
- file names,
- directory separators,
- file modes,
- symlinks,
- empty files,
- deletions,
- renames,
- binary files,
- executable bits,
- path normalization.

A useful conceptual model is:

```text
Canonical Change Representation
        ↓
Canonical serialization
        ↓
Cryptographic digest
        ↓
Approval / audit reference
```

Without canonicalization, two technically equivalent representations can produce different digests or, worse, inconsistent security decisions.

The exact serialization format can be chosen during implementation.

---

# 7. P0 — Repair Loop Must Invalidate Previous Approval When the ChangeSet Changes

The current run flow includes:

```text
ValidationFailed
    ↓
RepairProposed
    ↓
RepairApproved
    ↓
StagingCreated
```

This is directionally correct but needs stronger semantics.

If the repair changes the proposed mutation, then:

> the previous ChangeSet approval must not remain valid.

Recommended model:

```text
ValidationFailed
      ↓
Repair Proposed
      ↓
New ChangeSet / ChangeSet Version
      ↓
New Digest
      ↓
New Approval
      ↓
New Stage
      ↓
Validation
```

Every change to the actual mutation set must produce a new digest and require the appropriate re-approval.

Do not let a repair loop silently mutate an already-approved ChangeSet.

---

# 8. P0 — "Atomic Apply" Needs More Precise Semantics

The plan currently describes applying the validated ChangeSet to the target working tree.

The word "atomic" should be used carefully.

A multi-file working tree update is not automatically transactionally atomic merely because the operation is implemented through a patching tool.

## Recommendation

Define the Apply contract explicitly.

At minimum:

1. Verify target base state.
2. Verify no conflicting uncommitted changes.
3. Re-validate ChangeSet digest.
4. Re-check policy.
5. Apply in a controlled manner.
6. Detect partial failure.
7. Roll back or restore from known pre-apply state when possible.
8. Record the resulting repository state.
9. Never overwrite unrelated user modifications.

Consider whether the preferred long-term mechanism should be:

```text
Dedicated Git worktree/branch
      ↓
Apply ChangeSet
      ↓
Validate
      ↓
Create Git commit
      ↓
Human merge/cherry-pick/fast-forward
```

or whether direct working-tree application is required.

The plan should choose one default model rather than leaving this ambiguous.

---

# 9. P0 — Event Store Must Have One Canonical Source of Truth

The plan currently uses:

```text
SQLite
+
JSONL
```

and also describes the event stream as the source of truth.

Two independent stores can diverge.

## Recommendation

Choose one canonical event journal.

For example:

```text
SQLite = canonical event/run store
JSONL = append-only export/audit mirror
```

or:

```text
JSONL = canonical event log
SQLite = derived query/index store
```

Do not describe both as equal sources of truth.

Also define:

- event IDs,
- sequence numbers,
- timestamps,
- schema versions,
- correlation/run IDs,
- idempotency,
- ordering,
- recovery after crash.

---

# 10. P0 — Recovery Semantics Need to Address Side-Effect Boundaries

The current design includes crash recovery.

However, consider a crash here:

```text
ApplyChangeSet
      ↓
files modified
      ↓
process crashes
      ↓
"ApplyCompleted" event not persisted
```

On restart, the platform must not blindly retry the operation and create a second inconsistent mutation.

## Recommendation

Define a side-effect protocol such as:

```text
Intent recorded
      ↓
Operation executes
      ↓
Result recorded
      ↓
Repository state reconciled
```

On startup:

```text
unfinished operation
      ↓
inspect actual repository state
      ↓
determine whether operation:
    not started
    partially completed
    completed
    diverged
      ↓
resume / rollback / require human intervention
```

This is important to make "crash recovery" a real guarantee rather than merely persisted checkpoints.

---

# 11. P0 — Execution Isolation Is Not Equally Enforceable on All Platforms

The plan currently proposes:

- working-directory confinement,
- environment sanitization,
- network restrictions,
- resource limits,
- timeout limits,
- isolated process invocation.

This is a good defense-in-depth architecture.

However, the ability to **strongly enforce** network, CPU, memory, child-process, and filesystem isolation differs significantly across operating systems and privileges.

Without a dedicated sandbox/container runtime, some controls may be:

- strongly enforceable,
- partially enforceable,
- advisory only.

## Recommendation

Do not claim universal strong sandboxing in the core.

Instead define execution capabilities by strength:

```text
Baseline Local Execution
    - cwd confinement
    - sanitized environment
    - timeout
    - process tracking
    - policy-controlled command invocation

Hardened Sandbox Adapter
    - stronger filesystem isolation
    - stronger network isolation
    - stronger resource constraints
```

The hardened implementation can use an optional OS/platform-specific adapter.

This preserves the no-mandatory-container requirement.

For untrusted repositories, the default should remain:

```text
no arbitrary project command execution
```

until the developer explicitly enables a supported execution mode.

---

# 12. P0 — The Agent Git Identity Is Attribution Unless Cryptographically Verified

The plan proposes:

```text
committed_by = Platform Agent Git Identity
```

and dedicated commit attribution.

This is useful, but Git author/committer metadata by itself is not proof of identity.

## Recommendation

Distinguish:

```text
Agent attribution
```

from:

```text
Agent authentication
```

If cryptographic auditability is required, define an optional signed-agent-commit mechanism.

Otherwise describe the identity as:

> a dedicated, convention-based attribution identity.

Do not imply that the string:

```text
Platform Agent <agent@local.internal>
```

itself proves that the platform created the commit.

---

# 13. P1 — Separate Platform Knowledge From Global Cross-Project Learning

The current plan correctly defers the global learning collector.

However, the original product vision included **global and local project-specific artifacts**.

The revised architecture should preserve that distinction without requiring a remote global learning service.

Use three levels:

```text
Platform Knowledge
    ↓
Versioned read-only knowledge shipped with the platform

Project Knowledge
    ↓
Git-versioned project-specific artifacts

Cross-Project Shared Knowledge
    ↓
Optional future synchronization/sharing
```

Examples of Platform Knowledge:

- reusable architecture patterns,
- known framework patterns,
- generic migration patterns,
- generic troubleshooting patterns,
- diagram templates,
- workflow templates.

This can remain local and versioned with the platform distribution.

The optional future global collector is a different concern.

---

# 14. P1 — The Current Plan Still Contains Project-Specific Coupling

This is an important alignment issue.

The current scope section names:

> `Migration & Refactoring Workflow (Ember Classic to Angular Standalone slice).`

This is too specific for a project-neutral platform plan.

That concrete migration is appropriate as:

```text
Example Workflow
```

or:

```text
Project-Specific Workflow / Extension
```

but should not appear as a defining workflow of the reusable core platform.

## Recommendation

Change the platform roadmap to:

```text
Migration & Refactoring Workflow
```

and move:

```text
Ember Classic → Angular Standalone
```

into a separate project-specific extension/example document.

This is important because the original architectural requirement is that the first project should not define the core platform's architecture.

---

# 15. P1 — The "Serverless" Terminology Should Be Clarified

The architecture correctly avoids a centralized backend.

However, the local GUI uses:

```text
localhost HTTP/WebSocket
```

which means there is a local server/process serving the Control API.

That is not "serverless" in the strict architectural sense.

## Recommendation

Prefer terminology such as:

> **Local-first, no centralized backend, no mandatory remote service.**

This is clearer than "100% serverless."

The intended architecture is still valid:

```text
Developer workstation
    ↓
local process
    ↓
local Control API
    ↓
local core
```

No cloud or centralized platform server is required.

---

# 16. P1 — Control API Needs Its Own Versioning Contract

The plan correctly creates a typed Control API, but the API will become the stability boundary between:

```text
GUI
CLI
future clients
Core
```

## Recommendation

Define:

```text
Control API Contract Version
```

and version:

- command schemas,
- query schemas,
- event schemas,
- errors,
- capability responses.

Prefer additive evolution where practical.

The GUI should declare which API contract version it supports.

This will make the standalone UI independently upgradable without coupling it tightly to the core engine.

---

# 17. P1 — Local GUI Security Needs Explicit Browser Threat Modeling

The plan already specifies:

- localhost binding,
- short-lived capability token,
- current OS user,
- current Git identity,
- GUI cannot bypass the core policy engine.

That is good.

Add explicit local-browser protections.

At minimum consider:

```text
loopback-only binding
+
unpredictable session token
+
per-launch session
+
Origin validation
+
CSRF protection for state-changing operations
+
WebSocket authentication
+
token expiry/revocation
```

Also ensure that sensitive operations are revalidated by the core even if the GUI token is valid.

The GUI must remain an untrusted client.

---

# 18. P1 — Artifact Ownership and Generated Documentation Need Explicit Rules

The plan generates architecture documentation and diagrams.

It should explicitly distinguish:

```text
Generated
Human Authored
Human Modified Generated Artifact
```

Otherwise an architecture regeneration could destroy valuable manual corrections.

## Recommendation

Give artifacts metadata such as:

```text
artifact_type
source
ownership
generated_by
last_generated_from
human_modified
generation_policy
```

And define regeneration behavior:

```text
Purely generated artifact
    → safe to regenerate

Human-modified artifact
    → show diff / require merge

Human-authored artifact
    → never overwrite automatically
```

Apply the same model to Mermaid diagrams and other generated specifications.

---

# 19. P1 — Project Model Needs to Handle More Than One Simple Repository

The architecture assumes a target Git repository/project root.

For real-world adoption, consider at least:

- monorepos,
- multi-application repositories,
- nested projects,
- Git submodules,
- Git worktrees,
- generated/source directories,
- repositories with multiple build systems.

Do not implement all of these in the first phase.

But the project manifest should be capable of representing:

```text
Project
└── Workspace(s)
    ├── Repository
    ├── Root
    ├── Source Scope
    └── Toolchain
```

This prevents the project model from becoming permanently tied to:

```text
one repository = one application
```

---

# 20. P1 — Existing Project Adoption Needs Explicit Safety Preconditions

The plan correctly supports:

> existing-project adoption.

Add explicit preconditions.

For example:

### Inspection

Can operate on:

```text
clean or dirty repository
```

because it is read-only.

### Planning

Can operate on a dirty repository, but should record:

```text
base commit
worktree state
uncommitted changes
```

### Apply

Should normally require:

```text
expected base unchanged
+
no conflicting target modifications
```

or should explicitly switch to a dedicated Git worktree strategy.

This prevents an agent operation from accidentally interacting with unrelated human changes.

---

# 21. P1 — Challenge → Solution → Learning Needs a First-Class Lifecycle

The original product objective emphasizes that the agent should:

1. collect challenges,
2. analyze them,
3. find solutions,
4. put the solution in the correct place,
5. reuse the solution later.

The final plan has entities for:

```text
Challenge
Solution
Learning
```

but the roadmap focuses much more strongly on Learning than on the actual challenge lifecycle.

## Recommendation

Define:

```text
Challenge
    ↓
Analysis
    ↓
Candidate Solution
    ↓
Verification
    ↓
Resolution
    ↓
Learning Candidate
    ↓
Human Review
    ↓
Approved Learning
```

And define where each artifact goes.

For example:

```text
.agent/challenges/
.agent/solutions/
.agent/learnings/
```

or another normalized structure.

The key requirement is that:

> A solved challenge should be traceable into the reusable learning that resulted from it.

---

# 22. P1 — Contextual Interaction Needs a Formal Context Envelope

The plan says the GUI supports contextual Q&A, but the context passed to the agent should be formally modeled.

A useful conceptual structure:

```text
ContextEnvelope
├── project_ref
├── selected_entity
├── selected_artifact
├── relevant_work_item
├── current_run
├── active_policy_version
├── relevant decisions
├── relevant learnings
├── evidence references
└── user question/request
```

The system should not dump the entire project into every prompt.

Instead:

```text
User selects node
      ↓
Context resolver
      ↓
Relevant artifacts/decisions/evidence
      ↓
Context envelope
      ↓
Agent
```

This is important for both performance and correctness.

---

# 23. P1 — Knowledge Retrieval Needs a Clear Initial Strategy

The architecture intentionally defers a vector database.

That is reasonable.

But contextual Q&A still needs retrieval.

The plan should define an MVP retrieval strategy such as:

```text
Structured metadata
+
filesystem/path filtering
+
exact search
+
symbol/index references
+
approved learning lookup
+
decision lookup
```

Optional later:

```text
semantic embeddings
```

This keeps the core implementation simple while ensuring contextual Q&A is actually implementable without introducing a vector database.

---

# 24. P1 — Distinguish "Event-Driven Run State" From Full Event Sourcing

The plan calls the Run lifecycle event-sourced.

If all authoritative Run state is actually reconstructed from events, that is true.

If instead:

```text
SQLite state
+
event log
```

are both maintained independently, then it is better described as:

> **event-driven run state with append-only audit events**

unless full event sourcing is intentionally implemented.

## Recommendation

Choose and state one model:

### Full event sourcing

```text
Events = source of truth
Projection = derived
```

or:

### State + audit

```text
Run state = source of truth
Audit events = append-only record
```

The first is more powerful but also more complex.

Do not use event-sourcing terminology unless the implementation actually follows it.

---

# 25. P1 — Run State Needs More Terminal and Exceptional States

The current lifecycle includes:

```text
RunCompleted
RunAborted
ValidationFailed
```

Add conceptual terminal/exception states as appropriate:

```text
Cancelled
Denied
PolicyBlocked
BaseChanged
Conflict
Expired
ExecutionFailed
ValidationFailed
ApplyFailed
RecoveryRequired
```

This becomes important for both the GUI and CLI because "failed" is not enough to explain why a run stopped.

---

# 26. P1 — Policy Files Need Clear Responsibility Separation

The current topology contains:

```text
.agent/policy.json
.agent/access/
    roles.json
    principals.json
```

This is reasonable.

Make the distinction explicit:

```text
policy.json
    = what operations are allowed/blocked/approval-gated

access/*
    = who has which capabilities and who is trusted to change security policy
```

Avoid storing duplicate or conflicting authorization information in both locations.

The Policy Engine should combine them deterministically.

---

# 27. P1 — Workflow Definitions Are Also Security-Sensitive

The architecture protects:

```text
policy
access
```

but project-defined workflow/configuration can potentially change agent behavior.

A malicious workflow definition could effectively bypass intended behavior even if the Policy Engine is correct.

## Recommendation

Treat executable workflow definitions and tool capability configuration as controlled artifacts.

For example:

```text
.agent/workflows/
.agent/tools/
.agent/policy.json
.agent/access/
```

should have explicit modification policies.

At minimum, changing a workflow that can execute privileged tools should require the appropriate approval authority.

---

# 28. P1 — Git Hooks Need a Lifecycle Contract

The plan correctly says hooks are advisory guardrails.

The next missing details are operational.

Define:

- how hooks are installed,
- how existing hooks are preserved,
- how platform-managed hooks are upgraded,
- how hook tampering is detected,
- how hooks are removed,
- how multiple tools can coexist,
- whether a managed hook delegates to another user hook.

Do not blindly replace existing hooks.

A managed hook should ideally be composable.

---

# 29. P1 — Preserve the Original GUI Scope Explicitly

The final plan's Phase 3 GUI scope currently mentions:

- project tree,
- architecture,
- steps,
- learnings,
- diff,
- diagrams,
- chat.

The original product vision was broader.

The final GUI acceptance criteria should explicitly include, as applicable:

```text
Project overview
Objectives
Requirements
Workstreams
High-level steps
Low-level tasks
Current state
Progress
Agent activity
Challenges
Solutions
Decisions
Architecture
Documentation
Artifacts
References
Help
Next steps
History/audit
Contextual interaction
```

The original vision should not accidentally disappear merely because the architecture was narrowed.

The GUI can remain a control center without becoming a full project-management product.

---

# 30. P2 — Team Audit History Is Currently Local

The current state matrix stores active run state and audit data locally.

That is consistent with the local-first architecture.

However, this means:

```text
Git-shared project policy
```

and:

```text
local run audit
```

are not the same thing.

In a future multi-user environment, users may need shared visibility of:

- runs,
- approvals,
- agent actions,
- validation results,
- audit records.

This is not a reason to add a server now.

Document it explicitly as:

> **Future shared operational history may require a remote/shared store. This is outside the local-first MVP.**

That makes the deferred boundary explicit.

---

# 31. P2 — Global Learning Should Remain Deferred

The decision to defer cross-project learning is sound.

Keep:

```text
project-local learning
```

in the core.

Defer:

```text
global collector
cross-project synchronization
shared community knowledge
```

until the local provenance model has been validated.

A later export pipeline should be:

```text
Local Learning
      ↓
Eligibility classification
      ↓
Secret/sensitive-content checks
      ↓
Sanitization
      ↓
Human approval
      ↓
Optional publication/sharing
```

---

# 32. P2 — Optional Strong Sandboxing Should Be an Adapter

The platform should not require containers merely to preserve the local-first architecture.

However, strong isolation is valuable for untrusted repositories.

The best long-term abstraction is:

```text
ExecutionSandboxPort
```

Potential adapters later:

```text
NativeProcessAdapter
OSSandboxAdapter
ContainerAdapter
VMAdapter
```

This preserves the core platform neutrality.

---

# 33. Recommended Final Architectural Layering

The current architecture is good. The final plan should preserve approximately this conceptual separation:

```text
USER SURFACES
    │
    ├── CLI
    └── Local GUI
            │
            ▼
CONTROL API
    │
    ▼
CORE DOMAIN
    │
    ├── Project
    ├── Run
    ├── WorkItem
    ├── Artifact
    ├── Decision
    ├── Challenge
    ├── Solution
    ├── Learning
    ├── ChangeSet
    ├── Approval
    ├── Policy
    ├── AccessPolicy
    ├── Actor
    └── Context
            │
            ▼
ORCHESTRATION
    │
    ├── Workflow Engine
    ├── Run State
    ├── Event Processing
    └── Repair Loop
            │
            ▼
DOMAIN PORTS
    │
    ├── AgentRuntimePort
    ├── WorkspacePort
    ├── CommandRunnerPort
    ├── GitPort
    ├── StoragePort
    ├── PolicyPort
    ├── IdentityPort
    ├── ExecutionSandboxPort
    └── Control/API contracts
            │
            ▼
ADAPTERS
    │
    ├── LLM/Agent runtime
    ├── Filesystem
    ├── Git
    ├── SQLite/JSONL
    ├── Native process runner
    ├── Optional sandbox
    └── Diagram/documentation tooling
```

This should remain a conceptual boundary rather than an instruction to implement every interface immediately.

---

# 34. Recommended Final Architecture Invariants Additions

The current plan already has a strong set of invariants.

Add or clarify these:

### 24. Trusted Authorization Bootstrap

> Authority Keys cannot derive their own trust solely from the repository policy they authorize. Initial trust must be bootstrapped through a separately trusted local mechanism or equivalent root-of-trust process.

### 25. Base-State Binding

> A ChangeSet is valid only against the repository state for which it was generated. If the authoritative target diverges, approval is invalidated and the platform must re-evaluate the ChangeSet.

### 26. Repair Re-approval

> Any repair that changes a ChangeSet creates a new digest and invalidates the previous approval.

### 27. Canonical Event Store

> Exactly one event representation is authoritative; any alternate representation is a derived projection/export.

### 28. Apply Safety

> The platform must never overwrite unrelated user modifications in the target project.

### 29. Authentication Assurance

> Cryptographically verified identities and local-trust identities are distinct assurance levels with explicit operation requirements.

### 30. Generated Artifact Ownership

> Generated artifacts must not be silently overwritten after human modifications without explicit reconciliation.

### 31. Workflow Security

> Executable workflow definitions and privileged tool configuration are security-sensitive artifacts subject to Policy Engine controls.

### 32. Project Scope Neutrality

> Concrete business/project migrations belong to workflow extensions or example projects, not to the reusable platform core definition.

### 33. GUI Non-Bypassability

> Every security-sensitive GUI operation is re-authorized by the core and cannot be trusted merely because it originates from the localhost GUI.

---

# 35. Recommended Final Acceptance Checklist

Before declaring the architecture implementation-ready, confirm:

## Core

- [ ] Core remains headless.
- [ ] GUI is decoupled.
- [ ] No mandatory centralized backend.
- [ ] Target projects remain independently usable.
- [ ] Project-specific workflows are extension modules.

## Identity and Authorization

- [ ] Cryptographic identity is distinct from Git author metadata.
- [ ] Local-trust fallback has an explicitly lower assurance level.
- [ ] Authority-key trust bootstrap is defined.
- [ ] Role-to-capability resolution is defined.
- [ ] Policy changes cannot self-authorize.
- [ ] Approval and authorization are separate.
- [ ] Agent identity and human identity are distinguishable.

## Change Safety

- [ ] Every ChangeSet has a deterministic canonical digest.
- [ ] ChangeSet includes the expected base revision.
- [ ] Approval is bound to the exact digest.
- [ ] Repair creates a new ChangeSet/version.
- [ ] Base divergence invalidates approval.
- [ ] Apply cannot overwrite unrelated changes.
- [ ] Partial apply/recovery semantics exist.

## Execution Safety

- [ ] Command allowlist exists.
- [ ] Working directory is confined.
- [ ] Environment handling is defined.
- [ ] Secrets are not persisted.
- [ ] Network isolation limitations are explicit.
- [ ] Strong sandboxing is an optional adapter if required.
- [ ] Untrusted repositories default to restricted execution.

## State and Audit

- [ ] Git/project state and local runtime state are clearly separated.
- [ ] One canonical event store is defined.
- [ ] Event IDs/ordering/versioning are defined.
- [ ] Crash recovery handles side effects, not only checkpoints.
- [ ] Run failure/terminal states are explicit.

## Knowledge

- [ ] Challenge → Solution → Learning flow is defined.
- [ ] Learning provenance is mandatory.
- [ ] Observed/Inferred/Human-Confirmed states are preserved.
- [ ] Platform knowledge is distinct from project knowledge.
- [ ] Generated vs human-edited artifacts are distinguishable.

## Project Modeling

- [ ] New-project initialization is defined.
- [ ] Existing-project adoption is defined.
- [ ] Repository/workspace scope supports future monorepo/multi-root needs.
- [ ] `.agent/` ownership and Git inclusion rules are explicit.

## GUI

- [ ] GUI consumes only the Control API.
- [ ] GUI context selection maps to a formal ContextEnvelope.
- [ ] GUI supports the complete intended project information hierarchy.
- [ ] Sensitive GUI actions are re-authorized by the core.
- [ ] Local browser/session security is defined.
- [ ] Control API is versioned.

## Extensibility

- [ ] Domain ports are versioned.
- [ ] Workflow extensions do not require core modification.
- [ ] Provider-specific implementations remain adapters.
- [ ] Identity/storage/execution providers can evolve independently.
- [ ] Concrete first-project workflows do not leak into core architecture.

---

# 36. Final Feasibility Conclusion

## Overall

**Feasible.**

The architecture is now strong enough to proceed.

## No fundamental blocker

There is no architectural blocker requiring:

- abandoning Git-native governance,
- adding a centralized authentication server,
- adding a centralized authorization server,
- introducing a mandatory cloud database,
- turning the system into a distributed microservice platform,
- embedding the GUI inside every target project,
- or abandoning the headless core.

## Main implementation risks

The primary risks are now:

1. Incorrect trust bootstrapping for Authority Keys.
2. Overstating the security guarantees of local process execution.
3. Incorrect ChangeSet/apply semantics under repository drift.
4. Event/audit inconsistency.
5. Accidental coupling of project-specific migration logic into the reusable core.
6. Generated documentation overwriting human work.
7. Losing parts of the original GUI/interactive product vision during the architectural simplification.

These are all manageable.

---

# 37. Instructions to Antigravity / Codex

Use this review as the final architecture reconciliation pass.

## Required actions

1. Read the current plan and this review together.
2. Map each P0/P1/P2 recommendation to the current architecture.
3. Do not blindly implement recommendations.
4. Preserve strong existing ADRs and invariants.
5. Resolve contradictions explicitly.
6. Keep the architecture local-first and without mandatory centralized authentication/authorization services.
7. Keep Git as the durable project governance layer.
8. Keep the Policy Engine as the local enforcement point.
9. Keep hooks as guardrails rather than the ultimate security root.
10. Ensure the first project does not define the reusable platform core.
11. Keep deferred functionality clearly marked as deferred.
12. Update ADRs, domain model, security model, architecture diagrams, acceptance criteria, and roadmap where necessary.

## Do not start production implementation as part of this review

This task is to produce the **final architecture/plan**.

After reconciliation, report:

- Which findings were already covered.
- Which findings required changes.
- Which findings were intentionally rejected.
- Which ADRs changed.
- Which invariants changed.
- Which security/trust boundaries are now explicit.
- Which features remain deferred.
- Whether any blocker remains.
- Whether the platform can proceed to implementation.

---

# 38. Final Architectural Intent

The end state should remain:

```text
                  HUMAN / DEVELOPER
                         │
                 ┌───────┴────────┐
                 │                │
                CLI          LOCAL CONTROL UI
                 │                │
                 └───────┬────────┘
                         ▼
                    CONTROL API
                         │
                         ▼
                  CORE DOMAIN
                         │
          ┌──────────────┼───────────────┐
          │              │               │
       POLICY          WORKFLOW         RUN
       ENGINE          ENGINE          EVENTS
          │              │               │
          └──────────────┼───────────────┘
                         │
                      PORTS
                         │
        ┌────────────────┼───────────────────┐
        │                │                   │
       AGENT            GIT              WORKSPACE
      RUNTIME                              /EXECUTION
        │                │                   │
        └────────────────┼───────────────────┘
                         │
                         ▼
                  TARGET PROJECT
                   (independent)
```

The platform should remain:

> **local-first, Git-native, project-neutral, policy-controlled, human-governed, auditable, extensible, and independently removable from the target project.**
