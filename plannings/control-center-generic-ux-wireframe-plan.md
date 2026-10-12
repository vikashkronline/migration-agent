# Generic Control Center — UX and Wireframe Baseline

Date: 2026-10-06

Status: Proposed interaction baseline for review; no GUI implementation phase has started.

**Superseded navigation baseline (2026-10-07):** the [hierarchical UX specification](control-center-tree-ux-wireframe-plan.md) replaces the flat primary navigation below. The current [interactive source](control-center-wireframes.html) now follows that project tree. This document retains the earlier design rationale and historical prototype verification.

## Purpose and scope

The Control Center helps users understand agent work, track execution and make informed decisions. The platform core is generic. Migration is one extension on that base. Detailed code review remains in an IDE or pull request tool; the Control Center provides summaries, evidence, lightweight previews and exact approval context.

This design supplements the [master architecture plan](final/agent-platform-master-plan.md) and observes the current [phase boundary](../docs/phase-status.md). It does not claim that the legacy GUI is accepted, change phase completion records, or authorize implementation of future services. A later, explicitly requested GUI phase must reconcile legacy approval/apply and operational-store wiring before using it.

The [interactive wireframe source](control-center-wireframes.html) uses synthetic fixtures only. Open it in a browser to explore the five screens, two workflow examples and twelve states. Its controls change presentation locally. Approval, apply, execution, links to external review and agent responses are previews, not working platform integrations. The five screen designs below are the portable specification.

## Design decisions

1. Keep the shell project-neutral: Overview, Work, Run, Attention and Decision.
2. Keep project, task, run, operation and artifact selection consistent across views.
3. Show the current work, reliable completion evidence, blockers and next permitted action before detailed logs.
4. Use workflow-defined stages and evidence sections; do not hardcode Ember, Angular, migration phases, or seven-stage pipelines in common components.
5. Separate plan acceptance, execution consent, remote-data disclosure, exact ChangeSet approval and apply.
6. Present model statements as proposals with sources; verified results come from durable core records.
7. Keep review and approval distinct. An IDE or PR review is not automatically platform permission to apply.
8. Begin with one selected project. Multi-project fleet dashboards, embedded editors, review threads and plugin marketplaces are outside this wireframe scope.

## Shared shell

```text
Agent Platform | Project / branch | Resolved actor / assurance | Freshness
------------------------------------------------------------------------
Overview | Work | Run | Attention | Decision
------------------------------------------------------------------------
Project > task > run > exact artifact, where relevant
Persistent blocker / next action
Main workspace                             Optional context disclosure
------------------------------------------------------------------------
Evidence and next action remain tied to the selected scope
```

All project/root labels distinguish source, staging and operational artifacts. The app obtains references through the Control API, not browser filesystem access. Long digests have a shortened visual label with a full copyable value on disclosure. Actor identity is resolved by the core and is not an editable sign-off field.

Connection state and run state are independent. A disconnected client displays the last verified snapshot, its age and an explicit stale warning. It does not declare the run stopped or complete. All privileged actions remain unavailable until an authoritative refresh and capability evaluation succeed.

Navigation should restore context and use stable project/task/run/artifact URLs in implementation. Browser back/forward must work. Selection changes clear obsolete action targets, cancel superseded reads and reject late results for other selections.

## Screen 1 — Project overview

Question answered: What are we trying to achieve, where are we now and what needs me?

```text
Project objective / requirement reference              Open project context
6 tasks: 3 verified complete | 1 awaiting decision | 2 planned
------------------------------------------------------------------------
Needs attention                       Current work
Exact artifact requires approval      Selected task / stage / owner
Open decision                         Open run
------------------------------------------------------------------------
Workstream              Tasks and observed statuses
Documentation           Architecture map — awaiting decision
Verification            Evidence inventory — complete
------------------------------------------------------------------------
Recent meaningful activity, each linked to its run or artifact
```

Completion means the workflow's required postconditions have passed. Validated, approved, applied and completed are separate states. Do not infer completion from events, generated lines, confidence, elapsed time or the number of checks. Unavailable totals display as unknown. Counts use one snapshot and identify the denominator; estimates are labelled estimates. No synthetic percentage or ETA is required.

An empty project offers a read-only inspection/planning entry point and links to requirements. If mutation or initialization requires authority, show the core-provided reason and channel instead of silently writing repository metadata.

## Screen 2 — Work explorer

Question answered: How does this task relate to the objective, and what can I do next?

```text
Workstream / task list             Selected task
  Evidence inventory: complete    Objective / acceptance criteria
  Architecture map: selected      Workflow / status / latest run
  ADR draft: planned              Depends on: evidence inventory [complete]
                                  Enables: ADR draft [waiting]
------------------------------------------------------------------------
Summary | Evidence | References
Files/artifacts, provenance, decisions and unresolved questions
Open current run                       Ask about this task
```

Task rows are native links/buttons, not mouse-only clickable rows. A dependency list is the default; graph rendering is optional and must not obstruct task actions. Users can inspect independent or blocked tasks without starting them. Contextual Q&A shows the selected task, run and artifact before submission, includes citations and uncertainty, and cannot grant command or approval authority. Unavailable agent services display an explicit unavailable state rather than a fake answer.

Knowledge remains reachable through References and project context: objectives, requirements, technical/functional architecture, stack, ADRs, challenges, solutions, curated learnings and ownership-aware artifacts. Promotion of learning is a separate decision with validation provenance, not an automatic chat action. Policy and session diagnostics are read-only disclosures in this slice; elevated settings editing is deferred.

## Screen 3 — Run detail

Question answered: What is the agent doing, what evidence exists and why is it waiting?

```text
Task / run / current operation          Origin: CLI, MCP or GUI
Workflow-defined stages, with completed/current/blocked labels
------------------------------------------------------------------------
Current stage / operation              Next permitted action
Check progress and bounded duration    Open decision / diagnose / resume
------------------------------------------------------------------------
Summary | Checks | Artifacts | Activity
Check         Result       Scope / artifact version        Evidence
Typecheck     Passed       ChangeSet B                       Open report
Build         Running      ChangeSet B                       Open operation
------------------------------------------------------------------------
Context: relevant decision, repair attempt / budget, provider policy
```

Validation separates command success, browser evidence, model review and optional E2E. Show passed, failed, running, skipped, unsupported and unrun distinctly. Optional checks do not inflate required coverage. Diagnostics are bounded/sanitized; link to immutable evidence rather than expose raw environments or full prompts.

Each repair cites the failed check, attempt/budget and new artifact version; previous evidence/approval is invalidated where required. Provider/model activity and usage appear only if recorded, with unknown usage explicitly labelled. Native, container and restricted modes have accurate trust/isolation labels. Native consent and remote disclosure remain separate from source-change approval.

Cancel means a request until the core confirms termination. Resume is offered only at a verified resumable checkpoint and with current permission. RecoveryRequired never offers automatic retry/apply. No optimistic "applied" event is used as completion proof.

## Screen 4 — Attention queue

Question answered: What needs a human decision or diagnosis, and why?

```text
Needs action for this project
Type                  Task                    Reason / owner        Open
Exact approval        Architecture map        Verified artifact      Decision
Execution consent     Another run             Native execution      Consent
Failure               Evidence extraction     Check failed          Run
Recovery              Interrupted apply       Disk state uncertain  Recovery
```

The queue is derived from current core state. Show unresolved items; acknowledgement cannot clear a safety condition. Order recovery and blocking failures first, then actionable consent/approval, with deterministic time/ID tie-breaks. Expired or superseded requests remain in history with their reason. A reviewer sees the same records as the developer; capability determines actions, not a role-switching client.

Each item shows project/task/run, scope, freshness, actor/capability requirements and reason. An unavailable action has an explanation and an appropriate next step. Restricted operations do not expose an override-policy button. A missing trust/consent channel offers the documented trusted-terminal handoff.

## Screen 5 — Decision detail

Question answered: What exactly is being requested, on what evidence and under which authority?

```text
Decision kind / task / exact artifact / validity
------------------------------------------------------------------------
Change summary                       Approval context
Changed paths / operations           Resolved actor and assurance
Rationale and unresolved findings    ChangeSet digest / base fingerprint
Required checks + linked reports     Policy digest / validation binding
External IDE/PR/bundle review links   Requested action and expiry
------------------------------------------------------------------------
Request changes                      Continue in trusted approval channel
```

A lightweight read-only diff is optional. No embedded editor, thread system, merge tools or full repository browser is required. Review links/bundles identify the exact artifact and base. If an external tool cannot demonstrate which version was reviewed, label review correspondence as unverified; opening a link is not proof of review.

The confirmation channel must be independently trusted and not callable by the model. Mode A signing is required where policy demands it. Until a human-only GUI channel is accepted, use the existing trusted-terminal route. The GUI may prepare a request and show its durable status; it cannot fabricate an approval or upgrade Mode B to Mode A.

Approval does not automatically apply. After approval, present the requested apply scope and core-provided preflight eligibility as a separate action. Freshness, base, policy, validation, consent and capability are rechecked server-side. Unknown, stale or mismatched evidence blocks apply. A repaired artifact always has a different identity, so an earlier approval cannot carry over.

Request changes records scoped feedback and preserves the original decision history; a new repair proposal is subject to workflow policy. Notes cannot expand authorized scope or become raw commands.

## State matrix

These are presentation categories, not replacement domain enums. The Control API maps authoritative lifecycle states into explicit labels and available actions.

| State | Presentation | Permitted next step |
|---|---|---|
| Empty | No run/evidence yet; distinguish from query failure | Read-only inspect or create a plan when permitted |
| Loading | Skeleton/label; actions unavailable | Wait or navigate |
| Running | Current operation and required checks; no fabricated ETA | Inspect; request cancellation if supported |
| Blocked | Blocking dependency or missing consent and responsible actor | Open dependency/consent details |
| Failed | Failed check, artifact and bounded diagnostics | Inspect; bounded repair if permitted |
| Awaiting approval | Exact artifact and completed required evidence | Trusted approval handoff or request changes |
| Approved | Approval scope and freshness; apply remains separate | Inspect preflight; request apply if eligible |
| Completed | Durable postconditions and completion receipt | Inspect result/history |
| Disconnected | Last verified snapshot plus stale warning | Reconnect and reconcile; privileged actions disabled |
| BaseChanged | New source base; old stage/evidence/approval stale | Reinspect and replan; no reuse by default |
| PolicyBlocked | Denied capability/rule; preserve evidence | Inspect explanation; authorized policy process externally |
| RecoveryRequired | Uncertain/partial state, affected files and attempted rollback | Human inspection through trusted recovery procedure |

Expired session, unavailable service, empty result and offline transport are distinct errors. Errors remain visible beside the affected action, not only in transient toasts. A retry repeats the same command ID while reconciling its durable result; it does not create duplicate execution.

## Common base and extension seam

| Common presentation contract | Extension-supplied content |
|---|---|
| Project/task/requirement/run references | Domain-specific objectives and task wording |
| Stage IDs, labels, dependencies and observed status | Migration stages, documentation stages or other workflows |
| Artifact type, ownership, digest, evidence and versions | Source/target compatibility reports, browser captures, architecture diagrams |
| Required/optional check results and provenance | Framework-specific validation profiles |
| Available action, denial reason, capability and request identity | Workflow-defined operations approved by core policy |
| Context envelope, provenance and uncertainty | Workflow-specific questions and references |
| Exact approval binding and recovery information | No extension override of core safety |

Extension content uses a finite set of typed presentation primitives (summary, list/table, safe text, diagram, image evidence, report link and optional diff). It does not inject executable frontend code, raw HTML, provider SDKs or shell commands. Unsupported schemas produce a readable unsupported-version message and suppress mutation controls. These are design requirements, not new classes to implement in this task.

## Two walkthroughs through the same shell

### Generic architecture-documentation workflow

1. Overview shows the objective "Document verified project boundaries".
2. Work selects "Generate architecture map", depending on completed evidence inventory.
3. Run shows extension-defined inspect, outline, generate, validate, decide, publish and verify stages.
4. Attention links the exact generated documentation artifact to a decision.
5. Decision links ownership-aware diagram/text previews and evidence. Human-modified generated files require reconciliation; human-authored files remain protected.
6. Trusted approval and guarded publication are followed by verified results. Read-only Q&A has no publication or approval stages.

### Component-migration workflow

1. The same overview shows "Migrate the account component with preserved behavior".
2. Work selects "Account component" and exposes source/target information as extension content.
3. Run displays inspect, plan, stage, validate, decide, apply and verify labels from the migration workflow. Native execution consent precedes commands where required.
4. Required lint/typecheck/test/build and browser evidence, model review and optional E2E remain individually visible, bound to the same artifact.
5. A failed browser check leads to a bounded repair, a new ChangeSet and recaptured evidence. Prior approval cannot authorize the repaired output.
6. Decision summarizes changed files and links IDE/PR review; trusted exact approval and guarded apply follow.
7. Source drift leads to BaseChanged, not a force-apply button. Interrupted apply with unverified rollback leads to RecoveryRequired, not retry.

All stages and fixtures in the interactive companion are illustrative. Passing these walkthroughs as a design does not prove their runtime integrations exist.

## Responsive and accessibility behavior

- At desktop widths the Work view uses list/detail columns; secondary context is a disclosure, not a permanently competing third pane.
- At narrow widths navigation wraps, columns stack and tables remain within their containers. Shared project/task/run identity remains visible. Code/digest content wraps or uses a local scroll area without page overflow.
- Use semantic headings, native buttons/links, associated form labels and visible keyboard focus. Do not rely on coloured badges alone.
- Return focus to the initiating control after closing a dialog; manage focus and Escape in production dialogs. Reveal details through keyboard activation, never hover alone.
- Announce meaningful state changes with a polite live region without reading every log event. Keep error text adjacent to actions.
- Validate at 1024, 736, 375 and 320 CSS pixels, with zoom/reflow and both themes. A prototype check is not a complete accessibility audit.

## Implementation acceptance and sequence

Before implementing the full shell, settle the canonical read models and trusted human channel against existing application services. Do not rebuild policy or workflow state in Angular.

First vertical slice: read-only project/task/run navigation, checks/artifacts, Attention -> exact Decision -> trusted-terminal handoff -> durable approval status -> separately guarded apply result. Use one generic workflow and one migration fixture to prove the shell can remain common. Add operational actions only when the same core service is already supported and tested through CLI/MCP.

Required future acceptance journeys:

1. A new user identifies the objective, blocker and next action without reading logs.
2. A CLI/MCP operation appears in the GUI; reconnect replays missing events and reconciles a snapshot without duplicates.
3. Rapid task/run switching cannot mix artifacts or approvals; browser back restores the selected scope.
4. A reviewer opens exact external evidence, requests changes and sees a new artifact version and invalidated approval.
5. Stale base, changed policy, missing consent, expired session and unsupported evidence each block apply with a specific explanation.
6. Cancellation is not presented as complete before durable confirmation; resume uses verified checkpoints.
7. Partial apply preserves evidence and leads to human recovery; no automatic retry is offered.
8. A completed task is distinguished from merely validated, approved or applied work.
9. The shell works offline with bundled assets; keyboard/zoom/narrow-width journeys remain usable.
10. The generic and migration workflows use the same navigation and primitives without framework conditionals in common components.

This task delivers wireframes and a design specification only. No production components, adapters, API routes or phase acceptance claims are introduced. Repository phase quality gates apply when implementation is explicitly requested; prototype rendering and interaction checks are the relevant verification for this design task.

## Prototype verification — 2026-10-06

Local headless Chromium rendering checked 120 combinations (five screens x twelve presentation states x two workflow examples), with no JavaScript page errors. Forty additional layout combinations covered five screens and both examples at 1024, 736, 375 and 320 CSS-pixel browser widths, with no horizontal overflow detected at the prototype root.

Interaction checks verified the trusted-approval preview, scoped feedback preview, dependency-task selection and disabling approval for failed required evidence. Desktop decision/checks, mobile recovery and dark overview screenshots were visually inspected. These are prototype checks, not proof of backend integration, WCAG conformance or production acceptance. No repository phase quality gate or migration command was run because production behavior did not change.
