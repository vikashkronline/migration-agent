# Generic Control Center — Hierarchical UX and Wireframe Baseline

Date: 2026-10-07

Status: Common GUI implemented following explicit authorization on 2026-10-07, including modular Angular 21 features and the user-selected optional typed Git-owned project-work definition linked to workflow evidence. Final gates and remaining scope are tracked in the [implementation report](control-center-implementation-report.md). Illustrative module/foundation entities are not invented production data.

## Purpose and authoritative boundaries

Use the project hierarchy as primary navigation. Selecting a project, foundation, module, feature or step opens a dashboard/detail view appropriate to that level. Runs, attention and decisions are contextual views and shortcuts, not competing top-level project categories. Keep the platform common and generic; migration supplies workflow content through extensions.

The [interactive source](control-center-wireframes.html) contains synthetic feature-delivery and component-migration examples. Its controls change local presentation only. Platform diagnostics, evidence, approval, apply, Q&A and external code review are explicitly previews. It implements no new backend routes or services and does not prove production readiness.

This specification supplements the [master architecture](final/agent-platform-master-plan.md) under the existing [phase boundary](../docs/phase-status.md). Core safety remains authoritative. The subsequently authorized implementation corrects legacy GUI state/approval/apply wiring; its evidence is recorded separately rather than inferred from this prototype. The original Gemini file remains untouched.

## Primary information architecture

```text
Project overview

1. Foundation & Readiness
   Application setup & toolchain
   Shell, routing & integration
   Shared & common services
      Authentication service
      Observability integration
   Non-functional requirements

2. Functional Modules
   User Management
      Account feature
         Workflow-defined steps (expanded on demand)
      Profile feature
   Product Catalog

3. Architecture & Knowledge
   Objectives & requirements
   Architecture & dependencies
   Decisions & standards
   Challenges & learnings
```

These are configurable project groupings, not domain enums or mandatory module names. A documentation, refactoring or other workflow may supply different work groups. The shared model supports groups, tasks, dependencies, workflow steps, artifacts, evidence and decisions without framework conditionals. Even when developing the agent platform itself, project implementation work remains distinct from host/runtime health.

The implemented [project-work definition](../docs/project-work.md) now supplies
those optional declared groupings, ownership and criteria. One declaration may
own each workflow-linked task; missing evidence stays visible and nonexecutable.
Only recorded verified completion contributes to rollups. Declaration dependencies
explain planning scope without replacing the authoritative execution DAG. Editing
metadata remains an ordinary Git workflow, outside source inspection by the GUI.

Production routes own project/item/section and exact artifact/run context. Lazy
Angular features use a route-scoped signal store and cancellable reads; the
[development guide](../ui/control-center/README.md) records the structure and checks.
Ask supports cited selected facts; external provider reasoning and human approval
retain explicit CLI/host handoffs. The wireframe's synthetic responses are historical
examples, not implementation evidence.

Every group is selectable. Expand/collapse is a separate native button with an accessible name, expanded state and controlled branch ID. Selecting a group opens its dashboard; expanding it does not change selection. Blocked and planned items remain inspectable. Unavailable execution does not lock navigation.

Keep large branches collapsed until needed. Selecting a feature reveals its steps; dependency navigation opens the exact canonical prerequisite and expands its ancestor path. Search reveals matching ancestors. The attention filter retains grouping context and does not mark conditions resolved.

## Shared shell and contextual views

Header: platform brand, project/branch, actor/assurance, data freshness and a separate Platform Health entry.

Sidebar: project tree, find-item search, attention filter and evidence-based status labels.

Workspace: selected-item breadcrumb, compact Attention / Runs / Ask shortcuts, relevant status/blocker banner and the level-appropriate content.

Feature workspace sections: Summary, Steps, Checks, Artifacts, Activity and Decision. These remain bound to one selected feature, run and exact artifact. A feature with no run shows its dependencies and planning state, not another feature's run. A step opens its own scope/evidence view; the decision step can include the exact decision summary.

All nodes need a truthful destination. Unknown/unsupported detail displays an explicit unavailable state; it must never fall back to an unrelated setup pane. The prototype provides every declared node with a destination. Stable URLs, browser back/forward and cancellation of superseded server reads are future implementation requirements, not claimed prototype integrations.

## Control API read models and consistency

### Backend-owned tree projection

The application query boundary supplies a typed, project-scoped tree projection through the versioned Control API. It derives readiness, dependencies, evidence freshness, available actions and aggregate counters from authoritative application records and project governance through ports. It does not rely on the legacy GUI's repository-local database or its plan-only approval record. Missing project-work entities must be represented as unavailable/unscoped, not fabricated from a migration inventory.

The frontend owns sorting/disclosure presentation, selection, navigation and theme. It may arrange server-supplied groups but must not invent domain transitions, compute authorization, or infer required completion from events. Backend projection ordering and rollup denominators are deterministic and declared.

Tree headers include a schema version, project ID, snapshot/projection revision and durable journal cursor. Nodes include stable IDs, kind, parent reference, display order, status, child count/loading state, scoped readiness/summary counters, dependency references and navigation targets. Action descriptors include current capability/assurance requirements and blocking reasons. Framework-specific stages and evidence labels remain extension content. The projection is read-only; displaying an eligible action is not execution authorization.

Tree, children, node detail, ancestor-path lookup and search are required query capabilities. One possible route family is `/api/v1/projects/{project_id}/workstreams/...`; exact endpoint and model names are settled in the later implementation contract rather than mandating the review's proposed class names. Every query validates that project, node, run and artifact references belong together and respects applicable read capabilities and data classification. Detail is fetched against the requested artifact/version; an approval view must never silently substitute the latest artifact.

### Durable event reconciliation

Initial load obtains a consistent projection plus its durable journal watermark. Subscribe/replay from that watermark so updates between the query and stream connection are not lost. Events originate from committed authoritative records, including CLI/MCP work, and identify their schema, project, stream/cursor and affected entities. Process-local broadcaster counters are insufficient for restart/reconnect correctness.

Accept bounded invalidation events followed by versioned queries, or complete backend-generated projection patches. Fine-grained node updates are an optimization, not a requirement to create a second lifecycle model. If a patch is used, changed nodes and all affected rollups/action eligibility must correspond to one projection revision. Client-side arithmetic on an unverified `readiness_delta` is not authoritative.

Deduplicate replay, reject cross-project updates, ignore older revisions and detect cursor gaps/retention expiry. Reconcile with a fresh snapshot after a gap or uncertain state; suppress privileged actions while freshness is unknown. Preserve selection, expansion and scroll position across reconciliation. Coalesce affected queries rather than refreshing the whole tree on every transport heartbeat. Apply completion still comes from verified durable execution/postconditions, not a notification named `RUN_APPLIED`.

### Bounded loading and large-project behaviour

Load compact root/group headers and bounded child pages, with backend-provided summary counters. Fetch workflow-step headers when expanded and detailed checks/artifacts when selected. Keep diffs, screenshots, ARIA evidence and diagnostics out of the initial tree payload; load bounded, sanitized evidence through authenticated references on demand.

Specify deterministic paging, limits and an incomplete/unknown indicator. Failure to load a child page is distinct from an empty branch. Search and direct entry resolve an authorized item's ancestor path without loading the entire inventory. In-flight reads and caches are keyed by project, node, snapshot and artifact/version; superseded responses cannot overwrite the current selection. Do not retain large evidence for every visited item indefinitely.

Measure a representative large-project fixture during implementation, including expansion, search, selection, event bursts and evidence loading. Adopt viewport virtualization only if measurements warrant it and keyboard/accessibility behaviour is preserved; hundreds of nodes alone do not establish a performance failure. Root/module summaries must remain truthful when their children are not loaded.

### Deep links and history

URLs identify the project and stable selected-item ID, with validated optional run, artifact and view references. A route such as `/projects/:projectId/items/:nodeId` avoids coupling identity to a feature's current parent; the backend supplies its breadcrumb/ancestor path. The review's nested module/feature routes are illustrative alternatives, not a required domain hierarchy.

Direct entry and refresh resolve selection through the Control API even when the client tree is empty. Back/forward restores the selected context; reparenting retains stable identity. Missing, unauthorized, superseded or unsupported references receive explicit states instead of a root/setup fallback. Approval/evidence links retain the exact requested artifact and expose invalidation. Session tokens, approval credentials, raw source-root paths and secrets must not be encoded in navigation URLs. URL/view state never grants a capability or authority.

## Level-specific views

| Selection | Main content | Next action |
|---|---|---|
| Project | Objective, prerequisite coverage, feature completion, unresolved scope and current work | Open blocker, foundation or module |
| Foundation | Logical technical work order; readiness per dependent operation; optional/unrequired items | Inspect exact prerequisite or impacted feature |
| Shared group | Common capability status and links | Open service or evidence |
| Prerequisite | Implementation status, evidence freshness, owner and dependent work | Refresh evidence or inspect report through existing core service |
| Module | Each feature once, verified completion count, backlog and dependency reasons | Open feature |
| Feature | Acceptance criteria, required dependencies, current operation, run/ChangeSet and contextual sections | Inspect checks, exact decision or checkpoint |
| Step | Workflow-defined scope, observed state, prerequisites and artifact-bound evidence | Inspect evidence or feature decision |
| Knowledge group/reference | Requirements, architecture, ADRs, challenges/solutions/learnings and ownership | Inspect provenance and related work |

## Readiness and dependency rules

The tree expresses ownership. Dependencies are graph edges and links; do not duplicate shared services or features under each consumer. Display which operation is blocked, why, and which prerequisite resolves it.

Do not require universal 100% foundation completion for all work. Planning can remain available while preparation or integration validation is blocked. Apply always satisfies all policy-required safety gates. Optional observability can remain planned without blocking an unrelated feature; stale authentication evidence can block an operation that declares it.

Distinguish implementation progress from readiness. A shared service can be implemented while its verification evidence is stale. An accepted ADR is a decision, not proof that its implementation is complete. Native execution consent, remote-data disclosure and source-change approval remain separate conditions.

Platform Health contains agent runtime, session/trust, Control API and backend availability. Foundation contains technical work for the selected project, such as its shell and shared services. Passing doctor checks does not prove target-project shell readiness, feature acceptance, accessibility conformance or migration fidelity.

## Progress semantics and visual language

Use consistent semantic colour with readable text: green for verified completion, blue for active work/approved-but-pending states, amber for waiting/stale evidence, red for failure/policy denial/recovery, and neutral for planned or unrun work. Selection uses a distinct violet accent. Colours use theme-aware product tokens and never carry meaning alone.

Status labels at every level use current authoritative evidence. Project/module counts include each scoped feature once. A module with two features cannot inherit one run's "5/6 steps" percentage. Unknown feature scope is explicitly excluded from a defined denominator and shown as unscoped backlog.

The readiness coverage bar represents a declared count of prerequisite evidence only; it is not overall project progress. Optional checks remain outside required coverage. Validated, approved, applied and verified-complete are distinct. Last-known evidence is labelled historical when disconnected or invalidated.

## Decision scope and lightweight review

Decision includes requested action, changed paths/operations, acceptance evidence, resolved actor/assurance and exact ChangeSet/base/policy/validation binding. Detailed code editing and review stay in the IDE or PR tool; an optional lightweight read-only preview and review-bundle reference are sufficient for the GUI.

**Read-only review decision (2026-10-07):** the user selected an embedded read-only
diff viewer for the current GUI. Artifacts now provides lazy, per-file exact-base
diffs, changed-file navigation/search, unified/split views, numbered context hunks,
basic syntax colouring and explicit LF/CRLF/final-newline information. Mobile uses
unified view. Unsupported or oversized content is explicitly unavailable, with
no silent truncation or current-source substitution. Comments, editing, review
submission and a full embedded review workspace remain outside this decision.
Viewing a diff never grants human approval or changes the guarded apply contract.

External review must identify the exact artifact and base. Opening a link is not proof of review and does not authorize apply. Model-callable tools cannot produce human approval. Until a GUI human-only channel is independently accepted, the design uses the existing trusted-terminal handoff; required Mode A authority cannot be replaced by Mode B.

An in-browser human approval experience is a valid future usability objective, but OS username, authenticated loopback session and CSRF protection alone do not establish human intent or authorize exact changes. Mode B approval is permitted only where policy allows it and through an independently accepted human-only approval channel. Mode C remains inspection-only; policy-required Mode A uses the established trusted signing/verification mechanism and cannot be downgraded by the GUI.

Both assurance paths call the same application approval contract and persist actor, project/run/step, exact ChangeSet, base, policy, validation, requested action, expiry and single-use nonce bindings. The acceptance evidence must include rejection of model/tool-invoked approval, actor spoofing, replay, cross-project use, changed artifacts and expired assertions. Until those channel properties are established, keep the trusted-terminal handoff and display the concrete unmet requirement.

A pasted signature, if ever offered, is only proof material submitted through an accepted human channel; it cannot establish human intent by itself. Verify exact payload, trusted key, repository binding, revocation, expiry and policy independently. Do not request private key bytes, reuse a session token as an approval assertion, or invent an unsupported signing command. Existing Mode B terminal review does not establish a browser approval channel.

Approval and apply remain separate actions. Apply preflight rechecks scope, base fingerprint, current policy, exact validation, consent and capability. New repair artifacts invalidate old approvals. Request changes preserves the reviewed artifact/version and creates a separately governed proposal; feedback never becomes a raw shell command.

### Later stage — developer feedback and Request changes

**Deferred by the user on 2026-10-07:** complete manual acceptance of the current
GUI first. Keep the implemented diff viewer read-only. A later, separately
authorized stage will add a lightweight developer-to-agent feedback loop:

- Capture a comment, expected behavior and acceptance criteria against the bound
  project/task/run/ChangeSet digest. Optionally anchor it to a declared file and
  line range/hunk; retain the original artifact when code changes.
- Persist typed feedback outside source, with launcher-resolved actor, timestamps
  and explicit open/submitted/in-progress/addressed/verified/outdated states.
  A submitted request must be traceable to the resulting proposal and evidence.
- Provide an explicit **Request changes** action that sends selected feedback to
  the authorized host/provider workflow. Saving a comment alone does not start an
  agent or execute commands. Treat comment text as untrusted context, subject to
  scope, capability, secret-screening and provider-disclosure controls.
- Extend the application revision contract for requirement-driven changes to
  otherwise passing artifacts. The existing failed-validation repair contract
  cannot be used by fabricating a validation failure. Out-of-scope requests need
  a fresh governed plan instead of expanding an existing repair silently.
- Accepted revisions create a new ChangeSet and invalidate prior validation and
  approval. Stage, revalidate and obtain fresh exact human approval before apply.
  The developer confirms whether the revised artifact addresses the request;
  an agent's assertion alone cannot mark acceptance verified.

Acceptance will cover artifact/line binding, stale anchors, permissions and actor
spoofing, cross-project rejection, durable request deduplication, unchanged source
on comment submission, scoped proposals, and fresh validation/approval after a
revision. Full discussion threads, source editing, collaborative review and a
browser human-approval channel remain outside this lightweight stage. This entry
records future scope only; it authorizes no implementation during manual testing.

## Presentation states

The scenario selector changes fixture presentation, not real domain state.

| State | Required behaviour |
|---|---|
| Awaiting approval | Show exact decision evidence and trusted-channel handoff |
| Running | Show operation and check states without fabricated ETA |
| Failed validation | Failed required evidence visible; approval unavailable |
| Prerequisite blocked | Name/link stale prerequisite and affected operation; preserve inspect/planning navigation |
| Consent required | Show separate execution-consent request; no source-approval substitution |
| Approved, not applied | Show bound approval and separate apply-preflight action |
| Verified complete | Show durable completion receipt and postconditions |
| Base changed | Old stage/evidence/approval stale; reinspect and replan |
| Policy blocked | Explain denial; no force-apply override |
| Recovery required | Affected scope and attempted rollback; human recovery, no automatic retry |
| Disconnected | Historical snapshot and age; privileged actions unavailable; execution status unknown |
| Empty project | No fabricated progress/run; read-only inspection/planning entry point |
| Loading | Unknown coverage/eligibility until authoritative snapshot is reconciled |

Cancellation remains requested until the core confirms termination. Resume requires a verified checkpoint. Session expiration, unsupported evidence, unavailable services and transport disconnection have distinct explanations in production. The backend remains the authority for every action and state transition.

## Generic and migration walkthroughs

Generic fixture: User Management owns Account summary and Profile preferences. A workflow supplies Understand, Design, Prepare, Verify, Decide, Deliver and Confirm stages. Project readiness and shared dependencies are inspected through the same shell. Optional observability does not gate every feature.

Migration fixture: the same feature/module structures display UserCard component and UserProfile service, with extension-defined Inspect, Plan, Stage, Validate, Approve, Apply and Verify stages. Required lint/typecheck, tests/build and browser capture/review are presented separately from optional E2E. No Angular or Ember assumption enters the common navigation model.

For either fixture: inspect foundation -> follow dependency to feature -> inspect operation/checks -> open exact Decision -> external review/trusted approval handoff -> separate guarded apply -> verified completion. Failure, repair, source drift and recovery preserve traceability and require fresh evidence where mandated.

## Responsive and accessibility design

**Mobile navigation decision (2026-10-07):** desktop uses a persistent tree sidebar; mobile uses a navigation drawer, collapsed by default. The drawer opens from the logical start side through a clearly labelled **Project navigation** button and overlays the content instead of pushing it down or narrowing it. At medium widths content columns can stack; no permanent third panel competes for space.

The selected-item breadcrumb, current status and attention shortcut remain visible outside the drawer. Reopening it restores the selected item, expanded ancestor path and tree expansion state. Mobile and desktop use the same hierarchy, selection and dependency semantics.

The mobile drawer follows these interaction requirements:

- Selecting an item closes the drawer and opens that item's appropriate dashboard/detail view. Move focus to the selected content heading or equivalent meaningful target.
- Provide a labelled close button, backdrop dismissal and Escape support. Dismissal without selection returns focus to the **Project navigation** button and preserves the current content.
- While the modal drawer is open, keep keyboard focus within it, make background content inert and prevent background scrolling. A long navigation tree can scroll inside the drawer without clipping controls.
- Opening, dismissing or resizing navigation never starts, cancels or approves an operation. Moving between mobile and desktop preserves selection and expansion state and removes obsolete modal focus/scroll restrictions.

This replaces the earlier inline mobile disclosure. Historical prototype checks below demonstrate that disclosure; the authorized production baseline now implements the overlay drawer. Its browser/focus/resize acceptance is recorded in the implementation report.

All navigation and disclosures use native labelled controls with visible focus. Use semantic lists for the collapsible explorer; do not declare an ARIA tree unless implementing its complete keyboard interaction contract. Parent selection and expansion are separately keyboard-accessible. The prototype includes input labels, text status cues and a polite selection live region.

Long labels, paths and digests wrap; tables remain contained. Actions are available without hover. Dark and light modes retain contrast. Full keyboard/focus, zoom/reflow, screen-reader and production dialog checks remain later acceptance work; screenshot inspection is not accessibility certification.

## Future implementation boundary and acceptance

No speculative frontend infrastructure or backend classes are created by this design task. The later authorized GUI phase should use existing application services through typed versioned query/action contracts. The frontend does not access Git, filesystem, SQLite, staging or provider SDKs directly.

The first implementation slice should cover tree selection -> feature/check evidence -> Attention/Decision -> trusted approval handoff -> durable status -> separately guarded apply result. CLI/MCP/GUI must share authoritative operational state. Event replay, snapshot consistency, deduplication and scoped request identities are necessary before calling progress live.

### Frontend and packaging requirements

The production client follows the existing Angular 21 LTS baseline with Standalone components, OnPush change detection, Signals/computed state, `inject()` and modern `@if`/`@for ... track`/`@switch` control flow. Bootstrap 5.3 utilities supply presentation, and Angular owns menus, mobile drawer, dialogs and state. Mermaid remains strict, with no untrusted HTML/click execution. No third-party component library is part of this baseline; this preserves the master plan's separate-review option for a later justified addition rather than introducing an absolute lifetime prohibition.

Before claiming compilation, validate Angular/CLI/TypeScript/Node/RxJS/optional Zone.js compatibility and support, create workspace/build configuration, and run a real production build. The review found Angular 21 paired with TypeScript `~5.4.2`; the authorized implementation now uses compatible TypeScript `~5.9.3` and a resolved npm lockfile. Angular's [official compatibility table](https://angular.dev/reference/versions) requires TypeScript `>=5.9.0 <6.0.0` for Angular 21. The actual build/toolchain is recorded in the implementation report. Recheck the [support schedule](https://angular.dev/reference/releases) on upgrades.

Serve one reproducible Angular build through the loopback server with all baseline assets bundled for offline operation. The handwritten visualization is a design artifact, not a production bundle. Verify a production CSP without `unsafe-eval`, avoid permissive untrusted HTML insertion, and replace inline executable event handlers rather than weakening CSP to preserve prototype code. CSP/asset compatibility and safe diagram/evidence rendering need actual browser verification.

### Ordered implementation gates

1. Reconcile the existing GUI with canonical external operational state, shared policy/identity and exact approval/apply services. The legacy actor-derived plan hash and event-only apply method cannot authorize or prove exact apply. Confirm which project-work entities exist before choosing the minimal read-model seam.
2. Define/test typed projection, detail/search/paging, scoped action and snapshot/event contracts with offline fixtures. Include generic and migration examples, mismatched references, unknown scope and truthful unloaded rollups.
3. Establish the compatible Angular workspace, offline build and CSP before relying on browser integrations. Implement tree selection, deep links/history and the mobile drawer using those contracts.
4. Add level-specific views, bounded evidence loading and durable reconciliation. Keep detailed code review external; do not make a full editor, review-thread system or rich split-diff workbench a prerequisite.
5. Connect the accepted trusted-terminal approval path and guarded apply, then verify durable outcomes. A browser approval path is separate acceptance work and must pass the human-channel tests before replacing the fallback.
6. Run all six repository phase quality gates plus production frontend build, focused offline contract/interaction tests and measured browser acceptance. Verify direct links, event replay, selection races, large-project loading, CSP/offline assets, exact approval invalidation and mobile keyboard/focus behaviour before declaring the GUI accepted.

These gates define future work order; they do not authorize implementation, mandate speculative service classes, or change historical phase completion claims.

Acceptance must demonstrate correct dashboards for every node, independent expansion/selection, discoverable blockers, correct cross-links, no mixed run/artifact during rapid selection, scoped prerequisites, truthful aggregate counts, exact decision invalidation, recovery restrictions, external review correspondence and generic/migration reuse. Run the repository's required phase gates only when implementation is explicitly requested.

Mobile navigation acceptance must additionally demonstrate a closed-by-default overlay drawer, a full-width unobstructed content area when closed, correct selection and expansion restoration, close/backdrop/Escape dismissal, focus containment and return, automatic closure after item selection, readable long-tree scrolling and preservation of context across viewport changes. Breadcrumb, status and attention access remain available without reopening the drawer.

## Review disposition — 2026-10-07

The [architecture and UX review](control-center-architecture-and-ux-review.md) was assessed against the master invariants, current Control API/service/broadcaster, shared exact-approval models, trusted console adapter and frontend package manifest. The report remains an independent review; its proposed fixes are not automatically accepted instructions or implemented capabilities.

| Finding | Decision | Qualification incorporated above |
|---|---|---|
| Gap 1: backend tree projection | Accepted | Typed project-scoped query/read model over canonical application ports; endpoint/class names remain implementation choices, and unsupported project-work entities are not fabricated |
| Gap 2: fine-grained events | Accepted with changes | Durable cursor plus snapshot reconciliation; invalidation/refetch or coherent versioned patches; no client-authoritative readiness deltas |
| Gap 3: lazy loading | Accepted with changes | Bounded/paged headers and on-demand evidence; measure scalability before requiring virtualization; include search, unloaded rollups and cancellation/versioning |
| Gap 4: direct Mode B click / Mode A signature paste | Not accepted as sufficient approval proof | Improve GUI approval UX only through a verified human-only channel and shared exact approval contract; retain terminal fallback and policy-required assurance |
| Gap 5: deep links/history | Accepted with changes | Stable project/item identity with exact run/artifact context and authorized direct-load resolution; no mandatory migration-specific nested routes |
| Gap 6: frontend/build rules | Accepted with corrections | Existing Angular/Bootstrap/Mermaid baseline, compatible dependencies and measured production build/CSP; no blanket lifetime component-library ban or checked-off implementation claims |

Additional report corrections:

- The ownership tree is not the dependency DAG, and foundation is not a universal gate. Readiness is per operation; host/runtime health is separate from target-project foundation.
- The master plan's invariant 8 concerns durable knowledge, invariant 16 prohibits autonomous core self-modification, and invariant 19 separates authentication/authorization/approval. Controlled apply/recovery is invariant 28; confinement/distinct roots follows the staging/storage rules; learning evidence is invariant 35. Do not carry the report's incorrect labels into acceptance criteria.
- `RecoveryRequired` includes any partial or uncertain rollback, not only a special "double-fault" case. Job Objects supervise processes but do not establish native filesystem/network isolation.
- The existing local broadcaster uses process-local history/sequence; the reviewed Control API has no workstream route. Its approval method constructs an actor/plan/policy hash, and its apply method emits `RUN_APPLIED` without invoking the guarded apply service. The GUI startup opens repository-local checkpoints. These are integration gaps, not evidence that the future exact browser approval or cross-process event channel already exists.
- Browser capture, ARIA evidence or a mock viewport does not establish full WCAG conformance or a universally mandatory set of viewport sizes. Workflow/policy declares required coverage; missing or uncertain evidence remains explicit.
- Static prototypes and historical Python gates do not prove an Angular build or make this GUI production-ready. Full GUI implementation remains a separately requested phase; the report's implementation roadmap is qualified by the gates above.

## Prototype verification — 2026-10-07

Local Chromium checks exercised all 25 declared node destinations in both examples (50 destination checks), 114 presentation-state/context combinations and 40 layouts across 1024, 736, 375 and 320 browser viewport widths. No page-script errors or horizontal overflow were detected. Interaction checks covered independent selection/expansion, prerequisite navigation, evidence freshness, search, attention filtering, failed-check approval blocking, trusted approval preview and scoped feedback.

After adding compact mobile navigation, the same destination/state/layout checks were rerun. A preview theme reload interrupted screenshot capture after those checks; a focused follow-up verified dark-theme selection plus mobile tree show/hide, selection of the exact Apply step, automatic disclosure closure and unclipped content at 375 and 320 browser widths. Desktop feature/foundation/decision and full mobile recovery screenshots were visually inspected. These checks establish prototype behavior, not backend integration, live accessibility conformance or production acceptance. No source transformation or repository implementation phase gate was run.
