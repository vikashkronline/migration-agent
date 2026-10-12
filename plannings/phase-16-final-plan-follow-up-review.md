# Follow-up review of the revised Phase 16 implementation plan

Reviewed: 2026-10-04  
Source plan: `C:\Users\vkumar\.gemini\antigravity\brain\7a712a9d-3abf-40c9-b956-2a25f5e24a5f\implementation_plan.md`  
Scope: Remaining gaps in the revised plan, for incorporation before Phase 16 implementation. This review does not edit the source plan or implement Phase 16.

## Assessment

The revision addresses the broad issues in [the first review](phase-16-implementation-plan-review.md): it removes model-supplied approval booleans, binds tools to a project, introduces durable operation IDs, limits handoff to checkpoints, and separates host orchestration from server-side provider calls. The following findings concern **remaining contradictions or missing contracts**, not a request to repeat that work. Line numbers refer to the revised source plan.

**Confirmed product requirement:** Antigravity, Codex and comparable coding agents must contribute their own reasoning and coding capability to migrations, while the standalone CLI remains independently capable through its configured runtime. MCP is therefore more than a remote control surface for existing plans. The phase should prove both complete journeys against the same deterministic engine and safety policy. Client-specific integrations may differ, but Codex and Antigravity are required targets rather than optional future work.

**Priority:** P0 blocks mutating MCP tools; P1 blocks the claimed Phase 16 outcome; P2 is a documentation or compatibility correction.

## Remaining findings

### P0-1 — ChangeSet approval is described, but the existing approval path only binds a plan

**Evidence:** Revised plan lines 27, 37, 116 and 180 require an assertion over the exact ChangeSet and policy. In [planning.py](../src/migration_agent/application/planning.py), `approve_plan` signs `compute_plan_digest(plan)` and persists an `ApprovalSignature` with `plan_digest` (lines 190–231); Mode B can synthesize `sig:{actor}:{digest fragment}` (lines 206–207). In [transformation.py](../src/migration_agent/application/transformation.py), `apply` checks `verify_approval(plan)` (lines 391–399), then begins drift/preflight work. The new assertion is therefore not a simple MCP wrapper around the existing service.

**Incorporate:** Add a specific Phase 16C deliverable to define and persist an **apply approval record** bound to project identity, run/step, ChangeSet digest, policy digest, base revision and worktree fingerprint, validation result, action, actor, assurance level, nonce and expiry. Specify its signer and trust anchor for Mode A and the human-only session proof for Mode B. The application apply boundary must verify this record independently for **both MCP and CLI**, alongside the existing plan approval. Do not label a Mode B synthetic string “cryptographic human approval.” State how a repaired ChangeSet invalidates prior approval.

**Exit test:** An approved plan with an unapproved or repaired ChangeSet cannot apply through either interface; a valid approved ChangeSet can apply once; altered policy/base/validation fails before source writes.

### P0-2 — Human approval needs a trusted channel without depending on the future GUI

**Evidence:** Plan line 179 hardcodes `http://127.0.0.1:8080/review/<request_id>`, while lines 116 and 181 require a human-only assertion. The user has clarified that the full Control Center GUI belongs to a different phase and is not a Phase 16 dependency. Checked-in Control API/UI code does not establish an accepted GUI approval channel for this phase. A request ID in a URL is not authentication, and a model-callable endpoint that can complete approval remains scriptable even if the model cannot read the secret.

**Incorporate:** Define a **headless approval contract** owned by application services: approval request, exact ChangeSet/digest review data, accept/reject assertion, identity/assurance verification, one-use consumption and audit. For Antigravity/Codex, use a verified host-mediated human approval mechanism only if that host provides a human-only channel the model cannot invoke or forge. Otherwise use an existing trusted CLI signing flow or a narrowly scoped approval interstitial only if necessary for the Phase 16 in-IDE experience; do not build or depend on the full Control Center. Any local endpoint must have its own authenticated lifecycle, dynamic port, Origin/CSRF protection and no model-visible credential. Remove the hardcoded 8080 review URL until such a channel is designed and tested. The later GUI phase can consume the same approval contract.

**Exit test:** A model or unauthenticated process cannot approve by invoking MCP tools or possessing a review request ID; replay and cross-project use fail; supported host approval completes without exposing credentials to the model; standalone approval still works without a GUI.

### P0-3 — The old CLI bypasses remain in the shared application service

**Evidence:** Plan lines 38–39 and 117 call validation and clean-tree guards non-bypassable, but line 95 still advertises `--auto-approve`, `--skip-validation`, `--allow-dirty` and `--actor`. The current [MigrationPipelineService](../src/migration_agent/application/orchestration.py) skips the clean check with `allow_dirty` (lines 402–403), creates Mode B plan approval with `auto_approve` (lines 429–438), and can reach apply with validation skipped (lines 510–515 and 583–590). Prohibiting these flags in the MCP schema alone does not secure shared checkpoints and apply.

**Incorporate:** Put the final source-write preconditions in one application-level apply service used by CLI, Control API and MCP. Decide the disposition of each legacy flag explicitly: remove, restrict to preview/staging, or refuse final apply when it was used. Persist validation provenance and a clean-base check for the exact ChangeSet; do not convert `SKIPPED` or unavailable commands to `PASSED`. Ensure any Mode B automated plan sign-off cannot replace the separate human ChangeSet approval required for apply.

**Exit test:** Running CLI with all three bypass flags cannot create an applyable state that MCP can later consume, nor apply directly without the required ChangeSet approval and validation.

### P0-4 — Single-writer lease and SQLite idempotency need filesystem fencing

**Evidence:** Plan lines 119, 124 and 165–172 promise a SQLite lease and transactional outcomes. A SQLite transaction cannot atomically commit an external file patch or child process execution. A timed-out lease can be acquired by a second process while the first still writes, unless every writer uses a generation/fencing token and rechecks before each side effect. The current [checkpoint store](../src/migration_agent/adapters/checkpoints.py) has plans, approvals, checkpoints, events, ChangeSets, reports and runs, but no operation/lease schema yet.

**Incorporate:** Specify lease scope (project/run/step), acquisition transaction, owner identity, expiry/heartbeat, monotonic generation, stale-owner rejection, and how **all** CLI/MCP/Control API mutation paths participate. Persist an `APPLY_INTENT` before source writes, then reconcile disk versus expected digests and backups on startup. Record the idempotency key with a canonical argument digest and actor/project/tool scope; a repeat with changed input must reject. Do not claim “transactional” exactly-once filesystem effects—claim reconciled at-most-once behavior where proven. Define what a stale lease holder must do after losing ownership.

**Exit test:** Kill or suspend one writer after intent, let a second process start, then resume the first. Only one can mutate; reconciliation yields applied, rolled back or `RECOVERY_REQUIRED`, never duplicate patching.

### P1-5 — The MCP surface cannot initiate a new migration plan or use host reasoning

**Evidence:** The goal in lines 11 and 105–106 is ambient migration from a host agent. Phase 16A tools (lines 155–160) can show an existing plan and preview a step, while 16C tools (lines 176–180) can stage/validate/apply it. There is no `plan_create`, `submit_analysis`, `submit_plan_proposal`, or explicit prerequisite that a CLI user must first create the plan. The two-mode design in line 120 mentions host-submitted typed proposals, but no tool or validation contract implements that promise.

**Incorporate:** Add a complete host-orchestrated journey. Expose bounded eligible evidence/context reads, then typed submission of host-generated analysis, migration plan and (where needed) repair proposals. Validate evidence references, paths, scope, dependencies and policy deterministically before persistence or staging. Supply diagnostics and validation results back to the host so it can revise a proposal within explicit turn/repair budgets. Attribute every proposal to the host agent and retain the human approval boundary. The host can use its own model session without separate server API keys; the standalone CLI uses its configured `AgentRuntimePort` provider to perform the equivalent proposal steps. Both paths then share the same staging, validation, approval and apply services. Avoid a hidden fallback to fake output or a required CLI pre-step.

**Exit test:** Starting from the same adopted fixture, Antigravity and Codex can each inspect evidence, propose and revise a plan, and reach a validated staged ChangeSet through MCP; standalone CLI can do the same through its provider runtime. All three produce typed, evidence-checked artifacts and use the same apply gates. No ambient path requires an undocumented CLI step or separate server API key.

### P1-6 — Authorization matrix uses broad labels and marks sensitive reads “Public”

**Evidence:** Plan lines 198–210 use `Public`, `Operator` and `Verified Human Approval` as “Required Capability.” The [master plan](final/agent-platform-master-plan.md) requires granular capability checks (`project.read`, `changeset.stage`, `changeset.apply`, etc.; invariant 20) and distinct assurance levels. `plan_show`, `step_preview`, run status and validation diagnostics can disclose source paths, diffs and run state, even when the server is bound to one project. A `project_id` is a handle, not authorization.

**Incorporate:** Replace the column with **capability + minimum assurance + actor source** for every tool. At minimum distinguish inspection, planning, staging, command execution, approval request, cancellation and apply. Check the caller on every call, including status/polling, and scope handles to project and identity. Allow Mode C only for the specific read-only discovery that policy permits. Do not treat MCP client name or a host-provided actor string as identity; [MCP SDK guidance](https://ts.sdk.modelcontextprotocol.io/v2/migration/support-2026-07-28) describes client info as self-reported display/debug metadata.

**Exit test:** A caller with only read capability cannot see protected plan/diff/diagnostic data or poll another actor's operation; an `Operator`-like label alone grants nothing.

### P1-7 — Long-running operations have no complete start/result contract

**Evidence:** Line 121 promises `start_operation → operation_id → status/cancel`, but the tool list (lines 155–180 and 198–210) contains only `operation_status` and `operation_cancel`. `step_validate` returns a pass/fail result in the matrix, whereas large builds require an immediate durable handle. There is no result-retention, progress, cancellation, or restart mapping per operation. The official [MCP Tasks extension](https://tasks.extensions.modelcontextprotocol.io/specification/draft/tasks) is optional, so a plain-tool fallback needs a complete contract.

**Incorporate:** Define which tools start operations and whether their initial response is always an `operation_id`. Define states (`QUEUED`, `RUNNING`, `CANCEL_REQUESTED`, `SUCCEEDED`, `FAILED`, `RECOVERY_REQUIRED`), result fetch, retention, polling interval, progress units, timeout/resource bounds and safe cancel points. Specify whether 16B implements generic machinery only or a real validation operation; ensure each sub-milestone exit criterion exercises its deliverable. Avoid returning a final `pass/fail` from a request that can exceed client timeouts.

**Exit test:** Start a validation longer than the client's request timeout; the initial call returns promptly, a new MCP process can retrieve the final result, and cancellation ends at a safe boundary without losing audit state.

### P1-8 — Checkpoint list omits validation, repair and approval invalidation transitions

**Evidence:** Lines 119 and 170 list `PLAN_SAVED`, `STAGE_VERIFIED`, `APPROVAL_RECORDED`, `APPLY_COMPLETED`. A staged ChangeSet may fail validation, be repaired to a new digest, pass validation, and then require approval. “Approval recorded” alone cannot show that validation still matches the approved bytes. Master-plan invariants 25–26 invalidate staged output, validation and approval on drift/repair.

**Incorporate:** Define a transition table including at least `VALIDATION_RUNNING`, `VALIDATION_FAILED`, `VALIDATION_PASSED`, `REPAIRING`, `APPROVAL_PENDING`, `APPROVAL_RECORDED`, `APPLY_INTENT`, `APPLY_COMPLETED`, `BASE_CHANGED` and `RECOVERY_REQUIRED`. Persist each state's ChangeSet/policy/base/validation digests and allowed next actions. Mark only named **quiescent** states transferable. State when approval must be re-requested and when prior validation must rerun.

**Exit test:** Repaired output, altered policy, dirty source or a failed validation cannot advance using a stale checkpoint or approval, regardless of interface.

### P1-9 — Protocol and client compatibility are not pinned or measured yet

**Evidence:** Line 121 says “pin a supported Python MCP SDK version” but gives no version or protocol revision. Lines 226–232 call the matrix “Measured” while entries say “Target Primary”, “Supported Secondary” and “Experimental” without tested client versions, operating systems, protocol versions or results. **Codex is absent from the revised client matrix** despite being a required integration. Line 192 requires manual Antigravity/Cursor verification without a reproducible checklist or a condition for failure. The [2026-07-28 MCP release](https://blog.modelcontextprotocol.io/posts/2026-07-28/) changed the lifecycle and moved Tasks to an extension; version choice affects the actual transport and long-operation design.

**Incorporate:** Add **Antigravity and Codex as required rows** in the client matrix, with other desired hosts listed separately. Add a short 16A compatibility spike that records SDK package/version, supported protocol revisions and the exact client versions tested. Specify initialization/discovery, tool-schema, error and reconnect checks for each advertised host and OS, plus the host-reasoning proposal loop and human approval UX. Keep matrix status “planned” until tests run; promote to “supported” only with recorded evidence. Define whether the server implements 2025 and 2026 eras or one pinned revision, and verify with the official SDK transport.

**Exit test:** The matrix has date, version, OS, protocol, mode, test result and known limitations for each supported row; Phase 16 cannot be complete without tested Antigravity and Codex host-orchestrated journeys and a tested standalone CLI journey.

### P1-10 — Preserve standalone capability parity without duplicating the engine

**Evidence:** The revised plan's two-mode description (line 120) names a host-orchestrated mode and a configured server runtime, but the Phase 16 tool sequence and exit criteria do not compare either with the standalone CLI. If host agents own planning/repair behavior while the CLI has a separate path, they can drift in validation, policy and artifact format. If the MCP adapter simply invokes the CLI's model runtime, it fails the requirement to use Antigravity/Codex capability.

**Incorporate:** Make the application services the shared workflow boundary. Define a common typed proposal contract for `analysis`, `plan`, `changeset` and `repair`, regardless of whether the proposer is Antigravity, Codex or a standalone provider adapter. Host agents may reason and draft proposals with their native capabilities; the standalone agent must still discover, analyze, plan, stage, validate, repair within budget, request human approval and apply using its configured runtime. Keep provider/host SDK objects outside core contracts. Define a parity matrix of user tasks, input/output artifacts, safety gates and known capability differences; parity means equivalent supported workflow, not identical model output.

**Exit test:** An offline fixture completes both end-to-end modes with the same application-level validation and approval checks. Disabling MCP leaves standalone CLI migration functional; disabling a server provider credential does not break a documented host-orchestrated flow.

### P2-11 — Phase 15 metric names in the revised plan do not match the code

**Evidence:** Revised plan line 97 says `typescript_structure_rate` and `spec_structure_rate` were “added.” The current [evaluation model](../src/migration_agent/domain/evaluations.py), [evaluation service](../src/migration_agent/application/evaluation.py), [CLI](../src/migration_agent/cli.py), tests and [phase status](../docs/phase-status.md) still use `compilation_pass_rate` and `spec_pass_rate`. The checks described at line 98 are structural heuristics, not actual compilation or spec execution.

**Incorporate:** Since Phases 13–15 are marked complete, describe this as a **planned corrective rename** with backward-compatibility/schema-version handling, or retain the actual names and explicitly label them structural proxies. Do not write that the rename is already implemented. If the rename is in scope for Phase 16, list the affected public JSON/CLI fields, persisted benchmarks, tests and documentation. Otherwise schedule it separately and keep Phase 16 focused.

**Exit test:** Plan, code, CLI output, persisted schema and docs agree; no structural proxy is presented as a compiler pass rate.

### P2-12 — Quality and scope wording still overstates evidence

**Evidence:** Line 5 says “345 passed and 2 skipped tests across 6 required quality gates,” though 345/2 are `pytest` results and the six gates are separate commands. Lines 5, 8, 44, 68 and 98 use “production-grade,” “high-fidelity AST,” “full template migration” and “structural semantic” terms without a measured target-compiler or real-project fidelity gate in the revised plan. Line 11 says “lossless” checkpoint resumption, while line 170 explicitly permits `RECOVERY_REQUIRED` after an ambiguous apply. Phase 16D’s proposed skill is described as “enforcing” review (line 189), even though a skill is instructional and only the application policy can enforce it.

**Incorporate:** Say “Phase 15 recorded 345 passed, 2 skipped in pytest; all six required commands passed.” Describe supported transformation constructs and explicit unsupported cases, or add an offline Angular/TypeScript compilation gate before claiming compiler-level fidelity. Say “durable resumption at verified quiescent checkpoints, with explicit recovery state for ambiguity.” Describe the skill as guidance; security enforcement belongs to the server/application. Use the GUI Angular 21 baseline separately from generated target Angular 17+ compatibility.

**Exit test:** Each assurance claim has a corresponding recorded test or bounded compatibility statement.

## Phase boundary for the later GUI work

The full Control Center is **outside Phase 16** per the user's clarification. Do not add browser SPA components, Control API routes, WebSocket wiring, GUI tests, or GUI documentation as Phase 16 deliverables merely to complete MCP integration. The checked-in UI/Control API files may be treated as existing code to avoid accidental regressions, but their presence does not make them the required approval path or an accepted finished GUI. [Phase status](../docs/phase-status.md) currently labels Phase 10 / Control Center complete; reconcile that historical entry with the actual intended GUI phase and acceptance state before using it as implementation evidence.

Phase 16 should persist versioned, typed run, operation, ChangeSet, validation, approval and event records with enough provenance for CLI and MCP handoff. A later GUI phase can present these records and call the same application approval/apply services through its own authenticated Control API. That future phase should separately address GUI approval semantics, real apply wiring, cross-process event display and accessibility. Phase 16 completion must be demonstrable with Antigravity, Codex and standalone CLI **without launching the Control Center**.

## Suggested plan edit order

1. Resolve the shared apply approval and CLI bypass design (P0-1, P0-3).
2. Specify the review channel and signer/trust model (P0-2).
3. Define lease fencing, state transitions and long-operation responses (P0-4, P1-7, P1-8).
4. Specify the host proposal loop and standalone parity using shared typed services (P1-5, P1-10).
5. Replace broad capability labels and complete the Antigravity/Codex client matrix (P1-6, P1-9).
6. Correct historical implementation claims and quality wording (P2-11, P2-12).
7. Keep the full Control Center in its separate phase; define only the headless approval and state contracts that it can consume later.

