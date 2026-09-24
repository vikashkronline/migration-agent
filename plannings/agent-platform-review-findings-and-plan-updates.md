# Agent Platform — Architecture Review Findings & Recommended Plan Updates

## Purpose

This document is a follow-up architecture review of the current **Agent Platform** plan.

It is intended to be provided to **Antigravity / Codex** together with the current architecture-plan Markdown so that it can:

1. Review the findings below.
2. Compare them against the current plan.
3. Identify conflicts, overlaps, or incorrect assumptions.
4. Update the architecture plan where appropriate.
5. Preserve the original architectural intent unless there is a strong reason to change it.
6. Avoid implementation until the revised architecture and roadmap are internally coherent.

This document is **not** intended to replace the current plan. It is a set of findings and proposed corrections that should be evaluated and incorporated where justified.

---

# 1. Overall Assessment

The revised direction is substantially stronger and more coherent than the original concept.

The current plan has successfully moved away from an overly broad "AI development platform" toward a more focused:

> **Headless, Git-native agent execution, planning, verification, and engineering-control platform with a decoupled local GUI.**

The following architectural decisions are particularly strong:

- Project-neutral core.
- Headless core platform.
- Decoupled local web UI.
- No platform runtime code injected into target projects.
- LLM treated as an untrusted proposer behind a typed interface.
- Proposal -> approval -> staging -> validation model.
- Git-native project artifacts and decisions.
- Human-curated project learnings.
- Workflow modules over a shared core engine.
- Explicit separation between platform and target application.
- No uncontrolled autonomous self-modification.
- No mandatory remote server or cloud database for the local-first architecture.

The current conceptual architecture is therefore **feasible and worth continuing**.

There is no fundamental architectural or technological blocker that requires abandoning the direction.

However, several foundational contracts should be made explicit before Phase 2 implementation because leaving them ambiguous could lead to avoidable refactoring later.

---

# 2. Most Important Findings

The key areas requiring attention are:

1. Git state vs runtime/local state.
2. Git access vs application authentication/authorization.
3. Read-only inspection vs controlled mutation.
4. Repository `.agent/` state vs local runtime state.
5. Canonical domain model.
6. Run/Event model.
7. Policy as a first-class architectural concept.
8. GUI -> Control API boundary.
9. Safe command/process execution model.
10. Learning provenance and traceability.
11. Existing-project inference and confidence.
12. Extension/API versioning.
13. Global-learning timing and privacy.
14. Roadmap/phase numbering clarity.

These are not all blockers. They are mostly architectural clarifications that should be resolved before implementation of the corresponding capability.

---

# 3. Finding #1 — "Database-Free" vs SQLite Is Internally Inconsistent

## Current situation

The current ADR describes the architecture as:

> "Git-Native, Serverless & Database-Free Architecture"

but also defines:

- SQLite for local run checkpoints.
- JSONL for audit records.

SQLite is a database, even though it is embedded/local and does not require a dedicated database server.

The plan also says that all project state, configuration, and documentation live in Git, while separately defining local runtime state.

## Recommendation

Replace the conceptual term:

> "Database-Free"

with:

> **"Git-native and serverless, with no mandatory remote service or database."**

The intended distinction should be:

```text
Git = durable, versioned, shareable project state

Local Runtime Store = execution/runtime state
```

A recommended ownership model is:

```text
Git-versioned project state
├── Project manifest
├── Project configuration
├── Approved decisions
├── Approved project learnings
├── Architecture documentation
├── Human-curated artifacts
└── Other shareable project metadata

Local runtime state
├── Run checkpoints
├── Temporary agent context
├── Caches
├── Search/index data
└── Other non-shareable runtime state
```

## Architectural principle

Do not require every piece of state to be persisted in Git.

Do not require every piece of state to be stored in SQLite.

Each state category should have a defined source of truth.

---

# 4. Finding #2 — Git Should Not Be Defined as the Complete Authentication/Authorization System

## Current situation

The current ADR states that:

> "Authorization and authentication rely entirely on Git."

Git provides important security primitives around repositories, identities, signed commits, branch protections, and repository access, but it does not by itself provide complete application-level authorization for actions performed through the Agent Platform GUI/API.

Examples include:

```text
Who can approve a plan?
Who can apply a ChangeSet?
Who can modify platform policy?
Who can approve a learning?
Who can execute privileged operations?
Who can view a particular run?
```

These are application-level concepts.

## Recommendation

For the initial local architecture, it is completely reasonable to support:

```text
Single trusted local user
+
Operating-system account
+
Git identity
+
Repository access/permissions
```

and explicitly defer multi-user application RBAC.

However, the domain should have an authorization boundary so that future identity mechanisms do not force a core rewrite.

Conceptually:

```text
Actor
├── actor_id
├── identity
├── capabilities
└── authorization context
```

The initial implementation may use:

```text
LocalTrustedUser
```

Future adapters/providers may include:

```text
OIDC
GitHub
GitLab
Enterprise Identity Provider
Local Account Store
```

## Recommended architectural wording

> The initial local deployment assumes a single trusted operating-system user and delegates repository access/integrity to Git and the local environment. Application-level multi-user authentication and RBAC are outside the initial core. The platform nevertheless defines an authorization boundary so that future identity and authorization providers can be introduced without changing domain logic.

This preserves the lean architecture without prematurely building RBAC.

---

# 5. Finding #3 — Replace the "Read-Only Target Project" Terminology

## Current situation

The plan uses language such as:

> "Target projects are pure data"

and:

> "Mutations only occur in isolated staging areas."

The overall intention is correct, but the platform eventually intends to apply approved changes to the target repository.

Therefore the target project is not permanently read-only.

## Recommended lifecycle

Use the distinction:

```text
INSPECT
  ↓
Read-only observation

PLAN
  ↓
Read-only observation

APPROVE
  ↓
Approval bound to exact ChangeSet

STAGE
  ↓
Isolated mutation

VERIFY
  ↓
Tests / validation / policy checks

APPLY
  ↓
Controlled mutation of target repository
```

## Architectural invariant

> Agent analysis and proposal generation must never directly mutate the authoritative target working tree.

> All mutations must occur through an isolated ChangeSet/Staging workflow and require the appropriate approval/policy checks before being applied.

This is a stronger and more precise contract than calling the target project "read-only."

---

# 6. Finding #4 — Explicitly Separate Repository State from Local Runtime State

The plan uses `.agent/` metadata while also maintaining local SQLite/JSONL runtime state.

This is feasible, but ownership needs to be explicit.

## Recommended model

### Repository-visible `.agent/`

Store only information that should travel with the project and be version-controlled.

For example:

```text
.agent/
├── manifest/config
├── policies
├── project metadata
├── approved learnings
├── project decisions
└── other durable project-level metadata
```

### Local user runtime directory

Store:

```text
Local Agent Runtime
├── SQLite run state/checkpoints
├── caches
├── indexes
├── transient model context
├── temporary execution state
└── local UI/runtime state
```

## Important decision

Antigravity should explicitly define which `.agent/` content is:

- committed to Git,
- ignored by Git,
- generated/derived,
- temporary,
- user-specific,
- project-shared.

A recommended `.gitignore` strategy should emerge from this decision.

---

# 7. Finding #5 — Define a Canonical Domain Model

The plan currently contains many important concepts:

- Project
- Task
- Step
- Run
- Decision
- Challenge
- Solution
- Learning
- Artifact
- Workflow
- Agent
- Context
- Policy
- ChangeSet
- Approval
- Documentation
- Reference

However, their relationships are not yet defined as a canonical model.

This should be resolved before building the GUI and workflows.

## Recommended conceptual model

```text
Project
├── Work Item
│   ├── Step
│   └── Run
│
├── Artifact
├── Decision
├── Challenge
│   └── Solution
├── Learning
├── Workflow
├── Policy
└── Reference
```

And:

```text
Run
├── Project
├── Workflow
├── Actor
├── Context
├── Proposal
├── Approval
├── ChangeSet
├── Validation
└── Result
```

The implementation does not yet need to lock down a database schema.

However, the architecture should define:

- identities,
- relationships,
- lifecycle/state,
- ownership,
- persistence category,
- provenance,
- versioning,
- references between entities.

---

# 8. Finding #6 — Make Run/Event Persistence a First-Class Concept

The existing plan correctly includes append-only run persistence and audit digests.

This should be expanded into a first-class Run/Event model because it directly supports the future GUI, auditability, resumability, debugging, progress tracking, and contextual interactions.

## Recommended Run lifecycle

```text
RunStarted
    ↓
AnalysisCompleted
    ↓
PlanGenerated
    ↓
ApprovalRequested
    ↓
PlanApproved
    ↓
StagingCreated
    ↓
ChangesAppliedToStage
    ↓
ValidationStarted
    ↓
ValidationFailed / ValidationPassed
    ↓
RepairProposed
    ↓
RepairApproved
    ↓
ValidationPassed
    ↓
RunCompleted
```

The exact event set can be refined later.

## Recommended principle

The GUI should not maintain a second independent state machine.

Instead:

```text
Run Events
   ↓
Current Run State
   ↓
GUI presentation
```

This allows the same underlying run model to power:

- CLI status
- GUI timeline
- progress
- activity feed
- audit trail
- historical runs
- recovery/resume
- debugging
- contextual questions

---

# 9. Finding #7 — Make Policy a First-Class Architectural Concept

The current design already has:

- protected paths,
- command allowlists,
- approval gates,
- Git hooks,
- agent restrictions,
- learning approval.

These should not become scattered conditionals throughout the implementation.

## Recommended abstraction

```text
Policy Engine
├── Filesystem Policy
├── Command Execution Policy
├── Agent Capability Policy
├── Approval Policy
├── Git Policy
└── Learning/Knowledge Policy
```

The control flow becomes:

```text
Agent proposal
      ↓
Policy evaluation
      ↓
Approval requirement
      ↓
Human approval (when required)
      ↓
Staging
      ↓
Validation
      ↓
Apply/commit
```

## Why this matters

Policy is one of the main safety boundaries of the platform.

Making it explicit now prevents future logic from being distributed across:

- filesystem adapter,
- command runner,
- workflow modules,
- GUI,
- agent runtime.

The GUI should request actions; the core policy/domain layer should decide whether they are permitted.

---

# 10. Finding #8 — Define a Control API Between GUI and Core

The current plan proposes:

> standalone local web control center  
> localhost HTTP/WebSocket  
> connected to the local core

This is feasible and should remain.

The missing part is an explicit API boundary.

## Recommended architecture

```text
                 ┌───────────────┐
                 │      GUI      │
                 └───────┬───────┘
                         │
                    Control API
                         │
                 ┌───────▼───────┐
                 │ Control Layer  │
                 └───────┬───────┘
                         │
                 ┌───────▼───────┐
                 │ Core Domain    │
                 └───────┬───────┘
                         │
                       Ports
                         │
                 ┌───────▼───────┐
                 │   Adapters     │
                 └───────────────┘
```

The GUI should NOT directly manipulate:

- filesystem,
- Git,
- SQLite,
- staging workspace,
- agent runtime.

Instead, the GUI should use explicit operations such as:

```text
StartRun
GetRun
GetProject
GetArtifact
GetDecision
GetChallenge
AskContextualQuestion
ApprovePlan
RejectPlan
RequestChange
ApplyChangeSet
GetDiff
GetEvents
```

The exact API is for the implementation phase, but the boundary should be architectural now.

---

# 11. Finding #9 — Strengthen the Agent Execution Safety Model

The current design has an allowlisted command runner and bounded repair loop.

That is a good foundation.

However, allowlisting a command does not automatically make the underlying project execution safe.

For example:

```text
agent
  ↓
npm test
  ↓
package.json scripts
  ↓
arbitrary application code
```

Therefore the architecture should distinguish:

```text
Command Permission
```

from:

```text
Execution Isolation
```

## Recommended conceptual layers

```text
Execution Policy
      ↓
Command Policy
      ↓
Working-directory confinement
      ↓
Environment-variable policy
      ↓
Network policy
      ↓
Process/resource limits
      ↓
Timeouts
      ↓
Execution
```

Also consider explicit trust modes:

```text
Trusted Project
Untrusted/Unknown Project
```

This is particularly important for the existing-project adoption workflow.

The platform should never assume that repository code is safe merely because the agent was asked to run a familiar build/test command.

---

# 12. Finding #10 — Strengthen Learning With Provenance

The two-tier learning model is directionally good:

### Tier 1

Project-specific learning:

```text
draft → reviewed → approved
```

### Tier 2

Optional global learning:

```text
opt-in → sanitized → shared
```

The missing concept is provenance.

## Recommended Learning metadata

A learning should ideally be traceable to:

```text
Learning
├── ID
├── Title
├── Problem
├── Context
├── Proposed Solution
├── Evidence
├── Decision
├── Source Run
├── Source Commit
├── Created By
├── Reviewed By
├── Status
├── Version
└── Created/Updated timestamps
```

The agent should be able to answer:

> Why is this learning considered valid?

and:

> Which run, decision, or implementation caused it to be recorded?

This reduces the risk of accumulated unverified agent knowledge.

---

# 13. Finding #11 — Existing-Project Adoption Needs Confidence and Evidence

The existing project workflow is important and feasible.

The plan correctly includes:

- repository analysis,
- technology detection,
- project model generation,
- architecture documentation,
- existing documentation discovery.

However, generated architecture descriptions can contain inference.

The platform should distinguish at least:

```text
Observed
```

from:

```text
Inferred
```

from:

```text
Human Confirmed
```

## Example

```text
Authentication Service

Status: Inferred

Evidence:
- src/auth/*
- login routes
- authentication middleware

Confidence:
Medium
```

After human confirmation:

```text
Status: Confirmed
Confirmed By: User
```

This distinction should also apply to:

- technology detection,
- dependencies,
- architecture,
- components,
- workflows,
- security assumptions,
- generated documentation.

Otherwise inferred information can gradually become treated as fact by later agent runs.

---

# 14. Finding #12 — Clarify Extension Contracts and Versioning

The revised architecture correctly prefers a unified core engine plus workflow modules.

The current ADR states that migration/refactoring and architecture documentation share common primitives and should therefore use one core engine with specialized workflows.

That is a strong direction.

However, "future branches without core refactoring" should be expressed as a concrete architectural requirement.

## Recommended principle

> Core domain contracts and ports are stable, versioned extension points. Project-specific capabilities should normally be implemented through workflows, adapters, configuration, and documented extension interfaces rather than by modifying core domain logic.

Conceptually:

```text
Core Domain
     ↓
Versioned Ports / Contracts
     ↓
Workflow Modules
     ↓
Project Configuration
```

The goal should be:

> Normal future extensions should not require rewriting the core architecture.

Avoid the stronger promise:

> The core will never be refactored.

Refactoring will sometimes be necessary. The architectural goal is to make extensions additive and contract-based.

---

# 15. Finding #13 — Defer Global Learning Until the Local Model Is Proven

The Tier 2 global-learning collector is technically feasible.

However, it introduces a separate data-sharing problem into the platform.

The issues include:

- confidential source material,
- proprietary architecture,
- credentials/secrets,
- internal identifiers,
- customer data,
- re-identification risk,
- team sharing policy,
- retention,
- consent,
- data poisoning,
- trust in shared patterns.

## Recommendation

Do not make global learning a prerequisite for the core platform.

Prefer:

```text
Phase 1/2
Local project learning only

Later
Optional global learning export
```

A later system could use:

```text
Local learning
      ↓
Eligibility/classification
      ↓
Sanitization
      ↓
Human approval
      ↓
Optional global pattern
```

The local-first learning model can prove the concept without requiring the second system immediately.

---

# 16. Finding #14 — Fix the Roadmap Numbering

The current roadmap contains phase references that may become confusing.

It currently says:

> Phase 0 and Phase 1 are complete, ready for Phase 2

while the Major Phase 1 section references Phase 2, Phase 3, Phase 4, and Phase 5 objectives.

This is not an architecture problem, but it will create confusion for an implementation agent and for future developers reading the roadmap.

## Recommendation

Use one consistent numbering scheme.

For example:

```text
Foundation / Historical
- Phase 0 — Repository & architecture foundation
- Phase 1 — Headless core

Current roadmap
- Phase 2 — Architecture, knowledge, governance
- Phase 3 — Local control center GUI
```

Or:

```text
Foundation
- 1A Discovery
- 1B Planning
- 1C Staging
- 1D Validation

Phase 2
- Architecture & Knowledge

Phase 3
- GUI
```

Choose one scheme and use it consistently.

---

# 17. Architecture Invariants to Add to the Plan

I strongly recommend adding an explicit section called:

# Architecture Invariants

These should act as the "constitution" of the platform.

Recommended invariants:

1. **The LLM is an untrusted proposer.**
   - Core domain logic must not rely on the model to enforce safety or correctness.

2. **The core domain does not depend directly on an LLM provider.**
   - Models are accessed through `AgentRuntimePort` or equivalent interfaces.

3. **Proposal generation is read-only with respect to the authoritative target working tree.**

4. **Every proposed mutation is represented by a deterministic ChangeSet.**

5. **Every approval is bound to the exact proposed ChangeSet/version/digest being approved.**

6. **Approved mutations are executed through controlled staging and validation.**

7. **All privileged execution goes through explicit policy enforcement.**

8. **Durable project knowledge has a defined source of truth.**

9. **Runtime state is separated from Git-versioned project state.**

10. **The GUI is a client of the platform control API and does not independently manipulate platform internals.**

11. **Project-specific extensions use defined interfaces, workflow modules, configuration, or adapters instead of modifying the core by default.**

12. **Observed, inferred, and human-confirmed project knowledge are distinguishable.**

13. **Important agent actions generate traceable Run/Event records.**

14. **Secrets must never be written into Git-versioned project artifacts or learning records.**

15. **Platform version and project metadata/schema versions are explicitly tracked.**

16. **No autonomous self-modification of core platform behavior without explicit human-controlled change management.**

17. **The target project remains independently usable without requiring the Agent Platform runtime.**

18. **Platform removal must not destroy or invalidate the target project's application code.**

---

# 18. Recommended Architectural Layers

The revised plan can be clarified around these logical layers:

```text
┌───────────────────────────────────────────────────────┐
│                    USER SURFACES                       │
│                                                       │
│ CLI | Local Control Center GUI | Future API clients   │
└──────────────────────────┬────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────┐
│                    CONTROL API                         │
│                                                       │
│ commands | queries | subscriptions | approvals        │
└──────────────────────────┬────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────┐
│                    CORE DOMAIN                         │
│                                                       │
│ Project | Run | WorkItem | Artifact | Decision        │
│ Challenge | Learning | ChangeSet | Approval           │
│ Policy | Workflow | Context                            │
└──────────────────────────┬────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────┐
│                  ORCHESTRATION                         │
│                                                       │
│ state machine | event handling | workflow execution  │
└──────────────────────────┬────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────┐
│                  DOMAIN PORTS                          │
│                                                       │
│ AgentRuntime | Workspace | Storage | Git              │
│ CommandRunner | Policy | Identity                    │
└──────────────────────────┬────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────┐
│                    ADAPTERS                            │
│                                                       │
│ LLM/Agents SDK | Filesystem | Git | SQLite | JSONL    │
│ Process Runner | Mermaid | Other integrations         │
└───────────────────────────────────────────────────────┘
```

The actual implementation may differ, but the separation of responsibilities should remain.

---

# 19. Recommended State Ownership Model

Add an explicit state matrix to the plan.

| State / Data | Primary Source of Truth | Git Versioned | Local Runtime | Shared Across Users |
|---|---|---:|---:|---:|
| Project manifest | Project files | Yes | Cached | Yes |
| Architecture docs | Project files | Yes | Cached | Yes |
| Decisions | Project files | Yes | Cached | Yes |
| Approved project learnings | Project files | Yes | Cached/indexed | Yes |
| Current run | Run store | Optional summary | Yes | Initially no |
| Run checkpoints | Local store | No | Yes | Initially no |
| Temporary context | Runtime | No | Yes | No |
| Search indexes | Derived | No | Yes | No |
| Staging workspace | Temporary workspace | No | Yes | No |
| ChangeSet | Structured run artifact / Git-linked metadata | Yes or policy-defined | Yes during run | Potentially |
| Git commit | Git | Yes | Referenced | Yes |
| GUI preferences | User-local config | No | Yes | No |
| Policies | Project policy files | Usually yes | Cached | Yes if project-scoped |

Antigravity should refine this table rather than blindly adopting it.

---

# 20. Recommended Core vs Optional Capabilities

A useful boundary for the plan is:

## Core

- Safe filesystem inspection
- Path containment
- Project discovery
- Project manifest
- Typed domain ports
- Agent runtime abstraction
- Planning
- ChangeSet representation
- Approval mechanism
- Staging
- Validation
- Policy enforcement
- Run state
- Run/event persistence
- Git integration
- Project-level artifact management
- Project-level learning
- CLI
- Control API

## Optional / Workflow Modules

- Migration/refactoring workflow
- Architecture extraction
- Diagram generation
- Contextual Q&A
- Documentation generation
- Specialized agent workflows
- Additional repository/framework adapters

## Later / Outside Initial Core

- Multi-user RBAC
- Enterprise identity providers
- Centralized cloud service
- Global learning exchange
- Browser-based full IDE
- Enterprise ALM/project management
- Plugin marketplace
- Advanced semantic/vector indexing
- Remote/shared execution

This preserves the lean architecture described in the revised plan.

---

# 21. What Should NOT Be Added Because of This Review

Do not respond to these findings by accidentally recreating the over-scoped platform that the current plan intentionally avoided.

The architecture should NOT automatically expand into:

- Jira replacement
- Confluence replacement
- Backstage replacement
- Full web IDE
- enterprise identity platform
- centralized project database
- mandatory cloud backend
- autonomous self-rewriting agent
- complex plugin marketplace
- mandatory vector database
- mandatory microservice architecture

The goal is to strengthen the existing architecture, not broaden the product scope.

---

# 22. Feasibility Assessment

## Local-first developer platform

**Feasible.**

A practical implementation can remain:

```text
CLI
+
Headless Core
+
Local Filesystem
+
Git
+
Local SQLite
+
Agent Runtime Adapter
+
Workflow Modules
+
Local Web UI
```

No dedicated server or cloud infrastructure is fundamentally required.

## Existing-project adoption

**Feasible, with stronger execution isolation.**

The main challenge is safely analyzing and executing operations within arbitrary repositories, not the architectural model itself.

## Future multi-user support

**Feasible, provided identity and authorization are kept behind explicit boundaries.**

The initial system does not need full RBAC.

## Global learning

**Feasible, but should not be an early dependency.**

Keep it optional and later.

## GUI

**Feasible.**

The decoupled localhost UI is compatible with the headless architecture as long as it communicates through a control API and does not become a second implementation of the domain.

---

# 23. Potential Blockers

I do not see a fundamental architecture blocker.

The items that should be treated as **pre-implementation decisions** are:

### Critical

1. State ownership: Git vs local runtime.
2. Policy boundary.
3. ChangeSet/approval semantics.
4. Run/Event model.
5. GUI-to-core Control API.
6. Execution isolation/security model.

### Important

7. Canonical domain entities and relationships.
8. `.agent/` repository-state contract.
9. Learning provenance.
10. Existing-project observation/inference/confirmation model.
11. Extension contract/versioning.

### Can be deferred

12. Multi-user RBAC implementation.
13. Global learning collector.
14. Remote/cloud operation.
15. Advanced semantic/vector indexing.

None of the above requires abandoning the current direction.

---

# 24. Recommended Updated Roadmap Shape

## Phase 0 — Foundation

Completed/historical foundation:

- repository structure
- architectural boundaries
- basic ports/protocols
- safe filesystem inspection
- baseline configuration

## Phase 1 — Headless Core

- discovery
- planning
- ChangeSet representation
- digest-bound approval
- staging
- validation
- bounded repair loop
- Git integration
- policy enforcement
- run/event persistence
- project `.agent/` metadata
- project-level learning

### Phase 1 completion criterion

A developer can safely run the platform locally against a Git repository and obtain:

```text
Discovery
    ↓
Plan
    ↓
Approval
    ↓
Stage
    ↓
Validate
    ↓
Result
    ↓
Traceable Run/Audit
```

without requiring a web UI or external service.

## Phase 2 — Architecture & Knowledge

- architecture discovery
- observed/inferred/confirmed project model
- architecture documentation
- Mermaid source generation
- contextual Q&A
- knowledge/artifact navigation
- stronger Git governance
- contextual project references

Keep global learning optional or defer it.

## Phase 3 — Local Control Center

- local web application
- project tree
- run timeline
- task/step status
- artifacts
- architecture
- learnings
- challenges
- decisions
- contextual chat
- diffs
- approvals
- validation results
- diagram rendering

## Phase 4 — Extensibility & Ecosystem

Potentially:

- additional workflow modules
- framework adapters
- identity providers
- remote/shared execution
- optional global learning
- team collaboration

Phase 4 should only be expanded once the core abstractions have been proven.

---

# 25. Acceptance Criteria for the Revised Architecture

Before implementation moves significantly beyond the current phase, the plan should be able to answer "yes" to the following.

## Project neutrality

- Can the same core platform initialize multiple unrelated projects?
- Can projects define their own workflows without modifying core domain logic?
- Can the platform be upgraded without overwriting project-specific artifacts?

## Safety

- Is the LLM treated as untrusted?
- Are proposals separate from execution?
- Is every mutation represented as an explicit ChangeSet?
- Is approval tied to the exact ChangeSet?
- Can policy block an otherwise valid-looking agent proposal?
- Are command execution and process isolation explicit?

## State

- Is every major piece of state assigned a source of truth?
- Is repository state clearly separated from local runtime state?
- Can a run be inspected and resumed/recovered?
- Is important history traceable?

## Knowledge

- Are project and global knowledge separated?
- Are learnings versioned?
- Are learnings provenance-aware?
- Are observed/inferred/confirmed facts distinguished?
- Can the agent explain the source of a key learning or decision?

## GUI

- Is the GUI a client rather than a second domain implementation?
- Can the GUI render the same Run/Event state as the CLI?
- Can a user operate on contextual entities without direct storage access?
- Can the platform work without the GUI?

## Extensibility

- Are domain ports/contracts explicit?
- Are extension interfaces versionable?
- Can a new workflow be added without rewriting the core?
- Can an alternative agent runtime be introduced through an adapter?
- Can an alternative Git/storage/identity implementation be introduced later?

If these questions can be answered cleanly, the architecture is in a strong position for implementation.

---

# 26. Instructions to Antigravity / Codex

Use this document as an architectural review input.

**Do not blindly apply every suggestion.**

Instead:

1. Read the current architecture-plan document.
2. Read this review document.
3. Map each finding to the existing plan.
4. Identify which suggestions:
   - already exist,
   - are partially covered,
   - are missing,
   - conflict with current ADRs,
   - or are unnecessary.
5. Preserve good existing decisions.
6. Resolve contradictions explicitly.
7. Update ADRs and conceptual architecture where required.
8. Update the roadmap and phase numbering for consistency.
9. Add missing architecture invariants.
10. Add the canonical domain/run/state concepts at a conceptual level.
11. Keep deferred features explicitly deferred.
12. Do not expand the product scope merely to address these findings.

## Important constraint

**Do not start production implementation as part of this review.**

The objective is to produce an internally consistent architecture/plan first.

After updating the plan, report:

- what was changed,
- what was intentionally not changed,
- what remains unresolved,
- what architectural decisions are now considered stable,
- what decisions must still be made before implementation,
- whether any new feasibility/blocking concerns were discovered.

The final goal remains:

> **A reusable, project-neutral, local-first agent platform whose core can support future workflows and project-specific extensions without requiring fundamental architectural refactoring; whose agent actions are controlled, auditable, and verifiable; and whose GUI is a decoupled control surface over the same underlying platform state.**
