# Foundation and stack wizard — workflow alignment review

Date: 2026-10-09  
Reviewed specification: [foundation-stack-wizard-plan.md](foundation-stack-wizard-plan.md)  
Scope: Document and implementation inspection; no wizard implementation or migration execution.

## Verdict

**The feature is useful and broadly aligned with the migration goal, but the plan needs revision before implementation.** A guided inventory → target selection → dependency review → architecture preview flow can remove the current setup friction. Its read-only discovery, deterministic catalog, untrusted model proposals and API-only GUI are appropriate.

The execution design is incomplete. It does not explain how its new foundation task can run through the existing workflow, how generated files reach a destination while the original source remains read-only, or how governance acceptance differs from configuration, validation and apply. Several omissions could recreate the very problems the wizard is intended to solve: unsupported tasks, misleading readiness, overwritten decisions, repeated setup and missing prerequisites.

Keep the wizard as a presentation layer over shared application services. Revise its backend contracts and acceptance criteria before building the four screens. There is no need for a second migration engine, an independent approval mechanism or a separate task lifecycle.

## Review basis and interpretation

Reviewed the complete proposed plan, `AGENTS.md`, the authoritative master plan, current phase status, project-work and RBAC documentation, and relevant inventory, planning, knowledge, workflow, staging, validation, Control API and GUI code.

The findings below distinguish **confirmed integration conflicts** from **specification gaps or conditional risks**. The proposed wizard does not exist yet; this report does not claim an observed wizard exploit or failed implementation. The master plan contains historical in-repository governance layouts; for the requested read-only migration, the current external session/governance bindings and source-integrity requirement take precedence over copying that layout into the Ember source.

Priority meanings:

- **High:** Resolve before implementing activation or execution.
- **Medium:** Resolve in the implementation specification and focused acceptance tests.

## Findings at a glance

| ID | Priority | Type | Issue |
| --- | --- | --- | --- |
| F01 | High | Integration conflict / missing destination contract | Current apply writes to the bound source; wizard destination is unspecified |
| F02 | High | Confirmed integration conflict | Foundation initialization is not a supported shared task scope |
| F03 | High | Security and workflow gap | Browser confirmation is conflated with exact approval; capabilities are undefined |
| F04 | High | Governance gap | Accepted ADR precedence, collisions and supersession are unspecified |
| F05 | High | Readiness gap | Seeding configuration does not prove an executable, validated modern foundation |
| F06 | High | Correctness risk | Preset versions and replacement rules lack compatibility and semantic qualification |
| F07 | Medium | Coverage / modeling gap | “Entire dependency graph” exceeds the inventory contract and evidence model |
| F08 | High | Consistency gap | Mutating API has no exact proposal, revision, idempotency or recovery contract |
| F09 | Medium | Typed model / persistence conflict | Proposed ADR/package models do not match existing contracts or response examples |
| F10 | Medium | Confirmed projection risks | Launcher counts references; external governance and foundation grouping are not reconciled |
| F11 | Medium | User friction / access gap | Mandatory-looking setup, resets, resume and CLI/MCP parity are unspecified |
| F12 | Medium | Data disclosure gap | Optional model assistance has no explicit provider authorization or export boundary |
| F13 | Medium | Verification / scope gap | Milestones omit the foundation execution slice and adversarial acceptance criteria |

## Detailed findings

### F01 — Define the write destination independently from the original source

**Plan evidence:** Sections 2.1 and 2.4 promise read-only source inspection and generated `package.json`; section 5.3 identifies an external governance directory but does not identify where the modern workspace is created or finalized. See [plan line 22](<C:/Projects/New folder/migration-agent/plannings/foundation-stack-wizard-plan.md:22>) and [line 191](<C:/Projects/New folder/migration-agent/plannings/foundation-stack-wizard-plan.md:191>).

**Implementation evidence:** [MigrationSession](<C:/Projects/New folder/migration-agent/src/migration_agent/ports/governance.py:39>) distinguishes source, project/governance, staging and state. However, [WorkflowRuntime](<C:/Projects/New folder/migration-agent/src/migration_agent/adapters/workflow_runtime.py:79>) passes its bound project root to `LocalControlledFiles`; [apply_files](<C:/Projects/New folder/migration-agent/src/migration_agent/adapters/controlled_files.py:128>) writes to that adapter's `source`. Staging is a copy of the bound source, not an independently initialized modern workspace.

**Impact:** Reusing existing apply without an explicit destination design could overwrite the original manifest or write migrated code into the read-only Ember repository. Conversely, avoiding apply altogether would leave dependents unable to satisfy existing execution prerequisites. An external governance directory is not automatically the target application directory.

**Required revision:** Specify whether this slice only creates a staged foundation preview or also publishes a separate modern workspace. Bind every artifact and approval to its source evidence and authorized destination. Validate disjoint physical roots, links/junctions, path confinement and Windows path budgets. Keep governance and state outside application output. Define destination-base checks and recovery before enabling final writes; never silently rebind source to destination. A staging-only slice must explicitly describe what later execution remains unavailable.

### F02 — Seeding `step-001` does not make it executable

**Plan evidence:** [Section 5.3](<C:/Projects/New folder/migration-agent/plannings/foundation-stack-wizard-plan.md:194>) proposes a workspace/dependency/config initialization step. F1 constructs package configuration, but no milestone provides a foundation execution adapter.

**Implementation evidence:** [HostProposalService.submit_plan](<C:/Projects/New folder/migration-agent/src/migration_agent/application/host_proposals.py:209>) rejects scopes outside `component` and `service`, requires source-grounded expected files and rejects unresolved questions. [TransformationService.preview](<C:/Projects/New folder/migration-agent/src/migration_agent/application/transformation.py:117>) uses component/service extraction and rendering. [ApplyService.validate](<C:/Projects/New folder/migration-agent/src/migration_agent/application/apply.py:295>) requires dependencies to have `APPLY_COMPLETED` evidence, not merely a configured flag.

**Impact:** A wizard can show a seeded task that immediately fails `SCOPE_UNSUPPORTED`, cannot generate a workspace, or permanently blocks dependent validation. Naming a task `step-001` gives it no execution authority or prerequisite semantics.

**Required revision:** Add an explicit, bounded foundation workflow capability implemented behind framework adapters, with typed inputs, enumerated generated files, deterministic staging and appropriate allowlisted checks. Preserve existing scope rejection for unsupported constructs. Explain how foundation evidence satisfies downstream execution dependencies. Reuse the shared lifecycle, authorization, worker supervision and recovery machinery; do not weaken source-grounding requirements globally to admit this task. Make the foundation a dependency of affected functional tasks in the execution DAG, not only a first item in the GUI.

### F03 — Define authorization and human approval separately

**Plan evidence:** Section 2 refers to “maintainers” approving choices, section 5.3 directly writes accepted ADRs, and [section 6.2](<C:/Projects/New folder/migration-agent/plannings/foundation-stack-wizard-plan.md:238>) offers **Approve & Initialize Foundation**. The API milestones test session authentication but do not specify capabilities or an independent human approval channel.

**Implementation evidence:** The [master approval boundary](<C:/Projects/New folder/migration-agent/plannings/final/agent-platform-master-plan.md:88>) explicitly says session authentication and CSRF are not exact human approval. [RBAC capabilities and human-only actions](<C:/Projects/New folder/migration-agent/src/migration_agent/domain/access.py:17>) distinguish knowledge writes/acceptance, plan submission, staging, validation, signing, execution consent and rules management. Git maintainer status does not itself grant agent authority.

**Impact:** The button may suggest that a browser click accepts architecture, authorizes installation and approves target mutations together. Requiring owner signatures for every harmless draft would create the opposite problem: unnecessary ceremony.

**Required revision:** Provide an operation-to-capability matrix for inspection, draft recommendation, decision proposal, human decision acceptance, task seeding, staging, validation, consent and apply. Use current backend-derived permissions and recheck them before writes and during workers. Reuse the trusted-terminal handoff until an independent GUI human channel is accepted. Bind required approvals to the exact artifact/base/policy/validation/expiry/nonce; edits invalidate them. Security-effective changes to `.agent/config.json`, policy, rules or workflow definitions require the existing owner-signed Mode A path. Ordinary reports and local draft/state records should not acquire a new signing requirement. Distinguish **Save proposal**, **Accept architecture**, **Stage foundation**, **Validate**, and **Apply** in behavior and labels.

### F04 — Preserve accepted architecture and existing ADR identities

**Plan evidence:** The plan generates fixed `ADR-001`–`ADR-003`, presents a default target stack, and applies the selected choices. It does not describe reading accepted decisions, conflicts, human-edited records or supersession. See [line 18](<C:/Projects/New folder/migration-agent/plannings/foundation-stack-wizard-plan.md:18>).

**Implementation evidence:** [PlanningService](<C:/Projects/New folder/migration-agent/src/migration_agent/application/planning.py:73>) supplies deterministically ordered accepted ADRs to planning. [DecisionStatus](<C:/Projects/New folder/migration-agent/src/migration_agent/domain/knowledge.py:37>) already includes proposed, accepted and superseded records. The master plan preserves human-authored/modified artifacts.

**Impact:** Defaults could undo previously confirmed architecture, fixed filenames could overwrite an ADR, and accepted wizard output might never reach all planning/transform paths. “Auto-Suggest Defaults” is particularly risky after user edits.

**Required revision:** Load authoritative accepted decisions first, prefill compatible choices and show conflicts explicitly. Catalog defaults rank below accepted architecture. Allocate collision-safe decision identities; propose explicit supersession instead of overwriting. Preserve human edits with a diff. Version/digest the accepted stack selection and reference it from planning, foundation generation, functional transformations and validation. Verify that host-driven and standalone planning consume the same accepted architecture; provider prompting alone is not deterministic enforcement.

### F05 — Configuration, environment readiness and verified foundation are distinct

**Plan evidence:** [Section 5.3](<C:/Projects/New folder/migration-agent/plannings/foundation-stack-wizard-plan.md:195>) marks Architecture & Foundation “configured” after writing ADRs and seeding a task. The four screens do not cover toolchains, dependency acquisition or validation readiness.

**Implementation evidence:** [Doctor readiness diagnostics](<C:/Projects/New folder/migration-agent/src/migration_agent/application/doctor.py:32>) list missing execution backend, external native toolchain, offline dependencies, per-step consent and browser plan. They inspect configuration presence, not successful application builds. [Project-work progress semantics](<C:/Projects/New folder/migration-agent/docs/project-work.md:64>) distinguish declared work from verified completion.

**Impact:** The wizard can finish successfully while the user immediately encounters blocked validation. If “configured” is used to recommend functional migration, the workflow violates foundation-first ordering. Doctor `ok` is also insufficient proof.

**Required revision:** Return separate evidence for architecture acceptance, foundation task creation, environment prerequisites and validated base. Reuse existing readiness queries with actionable links to the missing prerequisite. Identify the package manager, lockfile, approved toolchain/dependency source and compatible version set. Generate the base through the agent, then run real relevant compile/build/test checks and applicable browser evidence before declaring it ready. Dependency installation is executable package code and needs the controlled command/consent path; a choice form is not that consent. Do not make catalog browsing or draft creation wait for executable validation. Any proposed headless-foundation exception to the current browser gate needs an explicit capability/profile decision, not a silent bypass.

### F06 — Qualify version compatibility and behavioral replacement rules

**Plan evidence:** [Catalog](<C:/Projects/New folder/migration-agent/plannings/foundation-stack-wizard-plan.md:100>) combines “Angular 17+”, `17.3+`, Vitest/`@angular/build`, an experimental data library and categorical replacements. RxJS is labeled native, and the text says reactive primitives supersede generator tasks and jQuery is prohibited.

**Implementation evidence:** The [Control Center package](<C:/Projects/New folder/migration-agent/ui/control-center/package.json:19>) uses Angular 21 with explicit related dependency and Node ranges. The master GUI baseline is also 21. This establishes the GUI baseline; it does **not** mean every migrated target must use the GUI's major version.

**Impact:** An open-ended `17+` preset cannot prove compiler, builder, TypeScript, Node and test-runner compatibility. A package rename does not preserve behavior: cancellation/concurrency policies, Ember Data identity/relationships, date parsing/time zones and Bootstrap/jQuery interactions need source-specific analysis. A compiler pass alone cannot certify those semantics. External RxJS must not disappear from the manifest because the strategy says “native.”

**Required revision:** Separate the agent GUI baseline from versioned target adapter support. Use a tested compatibility matrix and reproducible lock resolution for each supported target; unsupported combinations stay blocked with a reason. Document source references and catalog revision dates. Treat replacements as candidates with prerequisites, behavior obligations and alternatives, not unconditional equivalence. Experimental packages should be opt-in with a stable alternative. Project-specific prohibitions belong in accepted rules/ADRs. Define `NATIVE` precisely and track every actual runtime dependency. Keep framework-specific mappings in adapters: F0 already names `adapters/stack_catalog.py`, so reconcile section 4's ambiguous “core engine” wording rather than moving Angular knowledge into core.

No claim about current external package support dates is made in this review; compatibility must be verified when selecting and implementing a preset.

### F07 — Specify coverage rather than claiming the entire dependency graph

**Plan evidence:** Section 1 promises the “entire dependency graph,” but `LegacyDependency` has only name/version/category/dev flag and string paths. Section 5.1 returns an unexplained `unresolved_count`.

**Implementation evidence:** [ProjectInventory](<C:/Projects/New folder/migration-agent/src/migration_agent/domain/inventory.py:100>) already records dependency scope, manifest path, package boundaries, framework evidence and inventory issues. The current phase-status acceptance notes explicitly describe discovery as heuristic.

**Impact:** Flattening packages can merge identical names from different workspace manifests, lose peer/optional scopes, mistake a declared version range for an installed version, and classify absence of observed usage as proof of safe removal. Transitive dependencies, Bower/addons, custom build plugins and dynamic imports can remain invisible.

**Required revision:** Extend the existing inventory/read ports rather than introducing an independent scanner. Preserve package/manifest identity, declared versus resolved version, source evidence hashes/locations and evidence status. State which manifests, lockfiles, workspaces and usage patterns are supported, with bounded reads and explicit exclusions/parse failures. Distinguish unknown/unmapped packages from incomplete scanning. Unknown mappings should remain inspectable and block only affected execution scope. Do not require every unused development package to be translated before saving architecture. Keep discovery deterministic and offline by default.

### F08 — Bind activation to a reviewable proposal and make it recoverable

**Plan evidence:** Recommendations accept only preferences. `apply-foundation` has no typed request/response specification, proposal identifier, expected revision, digest, request ID or error/recovery semantics. It combines governance writes, task creation and a DAG refresh.

**Implementation evidence:** [WorkCommand](<C:/Projects/New folder/migration-agent/src/migration_agent/application/workbench.py:155>) and [WorkbenchService.dispatch](<C:/Projects/New folder/migration-agent/src/migration_agent/application/workbench.py:293>) use bound project/node identities, snapshot revision and idempotent receipts. [HostProposalService](<C:/Projects/New folder/migration-agent/src/migration_agent/application/host_proposals.py:140>) records principal, access digest and payload digest before leased execution.

**Impact:** A stale browser, second window, source/ADR drift, lost response or retry could accept different bytes, duplicate tasks, or leave ADRs accepted without an associated plan. Rewriting an existing DAG can invalidate staged artifacts and approvals.

**Required revision:** Specify immutable proposal IDs/digests, schema/catalog versions, source and governance revisions, active access/policy context and exact selections. Define fresh-context checks and typed failures with recovery actions. A mutating request needs a stable idempotency key, durable operation/receipt and replay rules; do not regenerate model recommendations at acceptance time. Use existing leases and access → apply → staging ordering where relevant. Define partial-write recovery and reconciliation across Git-owned governance and SQLite state. Never hold an access write fence while waiting for model/network work or user review. Existing staged plans need explicit invalidation/replan handling, not an in-place invisible DAG refresh.

### F09 — Reconcile models, ADR persistence and form vocabulary

**Plan evidence:** [Section 3.1](<C:/Projects/New folder/migration-agent/plannings/foundation-stack-wizard-plan.md:65>) uses permissive mutable models, unbounded strings/lists and `generated_adrs: list[dict[str, str]]`. Responses instead use `packages`/`draft_adrs`, whose shape differs from the domain model. Step 3 offers **Ignore** without a corresponding strategy and omits the model's **Custom** strategy. Native/removal recommendations still require a package name and version.

**Implementation evidence:** [ArchitecturalDecisionRecord](<C:/Projects/New folder/migration-agent/src/migration_agent/domain/knowledge.py:98>) is typed with status, context, consequences and provenance. [GitKnowledgeAdapter](<C:/Projects/New folder/migration-agent/src/migration_agent/adapters/knowledge.py:48>) loads JSON frontmatter, and [list_decisions](<C:/Projects/New folder/migration-agent/src/migration_agent/adapters/knowledge.py:190>) skips malformed records. Arbitrary Markdown with the correct filename is not necessarily a consumable ADR.

**Impact:** Previewed decisions can be silently absent from planning; UI choices can fail validation or erase unresolved obligations. Mutable or weakly bounded model output creates accidental path/package/config injection opportunities.

**Required revision:** Reuse typed ADR persistence and make drafts explicitly `PROPOSED`, including provenance and source/catalog references. Specify strict, versioned, bounded public models and consistent transport field names. Model a replacement outcome separately from its zero/one/many target packages, so removals and native outcomes need no fictitious package. Define custom/ignored/deferred outcomes and their execution consequences. Validate package coordinates, versions, unique identities and confined POSIX output paths; screen secrets and render model Markdown safely. Bind canonical digests to concrete generated bytes and ownership rules so ordinary CRLF differences do not produce misleading review noise.

### F10 — Replace reference counts with authoritative architecture/readiness projections

**Plan evidence:** [Launcher rule](<C:/Projects/New folder/migration-agent/plannings/foundation-stack-wizard-plan.md:215>) uses `archCount === 0` or an undefined unconfigured-foundation condition.

**Implementation evidence:** [SummaryPage](<C:/Projects/New folder/migration-agent/ui/control-center/src/app/workbench/item/summary/summary-page.ts:76>) counts general references, not accepted architecture decisions. A challenge or diagram can suppress the architecture prompt. Its foundation check considers direct child tasks. [Workbench references](<C:/Projects/New folder/migration-agent/src/migration_agent/adapters/workbench.py:725>) additionally discover governance by a conventional sibling path, while [project-work reads](<C:/Projects/New folder/migration-agent/src/migration_agent/adapters/project_work.py:22>) use the bound repository root. Neither establishes universal support for an arbitrary externally bound wizard governance directory.

**Impact:** Valid external ADRs may be missed; unrelated documents may falsely look like architecture; a newly seeded task may appear under ordinary work rather than foundation. The wizard could repeatedly launch, fail to launch, or recommend functional work too early.

**Required revision:** Supply typed, backend-derived accepted architecture and readiness projections from the actual session/RBAC governance binding. Distinguish missing, conflicting, unsupported and stale evidence. Resolve foundation grouping through canonical project-work/workflow references and include nested prerequisites. Do not expand UI heuristics or copy the sibling-directory convention into the new service. Include snapshot/event reconciliation and paging so partially loaded trees cannot determine readiness.

These are pre-existing projection limitations that the proposed integration must address; they are not evidence that the wizard already fails.

### F11 — Avoid repeated setup and preserve end-user channel parity

**Plan evidence:** The flow is linear, presents fixed stack paradigms and offers **Auto-Suggest Defaults**. There are no resume, skip, existing-workspace, cancellation or headless contracts; milestones describe API/GUI only.

**Impact:** Users with accepted ADRs or a working target can be forced to reconfigure. Reopening a modal can lose reviewed selections. Resetting all defaults can overwrite intentional custom choices. CLI/MCP users may need the browser or handwritten ADRs to finish the same operation.

**Required revision:** Keep guided setup optional and resumable using a versioned backend draft bound to project/revision. Adopt existing verified architecture and workspace evidence; only fill missing choices. Allow users to save an incomplete draft, defer affected custom translations and exit without applying. Make default suggestions a preview of changes to unchosen values, with explicit confirmation before replacing edits. Provide equivalent CLI commands and host proposal/read contracts over the same application services; human-only acceptance remains in the human channel. Use permission-aware read-only views and actionable denial reasons. Prefer a routed view for a lengthy wizard, or specify modal focus, keyboard dismissal, mobile layout and unsaved-change handling. Do not add Git-provider connection, remote branch protection, cloud databases or Docker as prerequisites for ordinary local stack inspection.

### F12 — Make model assistance an explicit, bounded optional operation

**Plan evidence:** Sections 1 and 2 allow model analysis of obscure packages and rationale generation, but no request indicates provider, authorized destination, exported evidence or cancellation/fallback behavior.

**Implementation evidence:** [Current access vocabulary](<C:/Projects/New folder/migration-agent/src/migration_agent/domain/access.py:25>) includes `provider.use`. Current phase status records that the live acceptance migration remains incomplete following an unapproved provider/destination request.

**Impact:** A seemingly local recommendation button could unexpectedly disclose source excerpts, stall without credentials or incur model calls on retries. Secret-bearing manifest values, scripts or URLs need special handling.

**Required revision:** Finish deterministic inventory/catalog output without requiring a model. Expose optional model assistance separately with provider/destination authorization, bounded sanitized evidence, payload digests and clear progress/errors. Do not export registry credentials, environment files, full lockfile URLs with credentials or arbitrary source by default. Model output must pass the same typed/evidence/compatibility checks and cannot supply executable shell commands. Failure should retain deterministic recommendations and clearly mark unresolved scope, rather than inventing a successful mapping.

### F13 — Strengthen milestones around the actual acceptance gap

**Plan evidence:** F0–F4 correctly place catalog implementation in adapters and include all six repository gates plus Angular tests. However, F1 mentions synthesis, F2 mainly authentication/payload tests and F4 a general end-to-end flow; none explicitly deliver the foundation execution and destination contracts identified above.

**Required revision:** Before GUI implementation, settle the destination, ADR acceptance, capability, readiness and supported foundation-task decisions. Add a bounded vertical backend slice that stages and validates a synthetic modern base through the production shared workflow. Then expose the API and wizard. Run focused tests as each behavior is introduced; retain the full required final gates and documentation updates. Add UI lint, format, production build, packaging of the new assets, and real desktop/mobile browser acceptance to GUI release evidence. Implementation authorization should name the chosen slice; reviewing this plan is not authorization to implement F0–F4.

At minimum, acceptance must demonstrate:

1. Source inventory hashes are unchanged after discovery, proposal, cancellation, validation and successful separate-destination publication; governance/state/staging never overlap source.
2. Unsupported foundation recipes and target versions fail before writes with an actionable reason; generated base can actually compile/build/test with recorded provenance.
3. Accepted ADRs beat defaults, colliding filenames and human edits survive, and supersession requires explicit human action.
4. Inspection-only, developer, reviewer, operator and owner actions obey current capabilities; browser sessions cannot sign; revocation stops affected workers safely.
5. Edited proposals, changed source/governance/access/catalog inputs and expired approvals invalidate old acceptance; retries do not duplicate ADRs/tasks.
6. Interrupted multi-store activation and unknown request outcomes recover coherently without declaring readiness or losing accepted decisions.
7. Missing toolchain/dependencies/consent/browser evidence guides the user to the exact prerequisite; functional tasks remain blocked by authoritative foundation dependencies.
8. Multi-package inventories, invalid/partial manifests and custom libraries preserve evidence and uncertainty; semantic replacement tests cover behavior rather than only package-name mapping.
9. Existing configured projects can resume or bypass redundant setup; suggestions preserve edits; deterministic operation works without network or provider keys.
10. Equivalent CLI/API/GUI flows use the same stored proposal and shared services; Windows/Linux path and line-ending cases pass offline fixtures. Real repository inspection must remain read-only and any actual execution requires the existing consent path.

## Recommended workflow after revision

| Stage | User experience | Authoritative result |
| --- | --- | --- |
| Inspect | View source packages, evidence and scan limits | Bound, read-only inventory |
| Propose | Prefill accepted architecture; preview compatible alternatives | Versioned stack draft with unresolved obligations |
| Review architecture | Compare ADR changes and resolve conflicts | Exact decision proposal; existing human acceptance path |
| Prepare foundation | Inspect generated workspace diff and prerequisite list | Supported foundation task and staged ChangeSet |
| Validate | Resolve environment prerequisites; run authorized checks | Real, current execution and applicable browser evidence |
| Approve and finalize | Review the exact validated artifact through the trusted human channel | Authorized publication to the explicit destination |
| Continue | Follow the next available task | Backend-derived readiness and topologically enforced dependents |

This separation describes evidence and user actions, not a new parallel lifecycle. It should reuse the existing operational records and projections.

## Review completion

Only this report was created. The proposed plan, platform code, GUI and selected source repository were not changed by the review. No migration, installation, provider call, approval, apply or quality-gate suite was executed. This is a specification review, not implementation acceptance.
